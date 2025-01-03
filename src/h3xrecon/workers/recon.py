import asyncio
import sys
from loguru import logger
from h3xrecon.core.worker import Worker, WorkerState
from h3xrecon.core import Config
from h3xrecon.core.queue import StreamUnavailableError
from h3xrecon.plugins import ReconPlugin
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from dataclasses import dataclass
from h3xrecon.core.utils import debug_trace
from typing import Dict, Any, Optional, Callable, AsyncGenerator
import uuid
from datetime import datetime, timezone, timedelta
import json
import importlib
import pkgutil

@dataclass
class FunctionExecutionRequest:
    program_id: int
    function_name: str
    params: Dict[str, Any]
    force: bool = False
    execution_id: Optional[str] = None
    
    def __post_init__(self):
        if self.execution_id is None:
            self.execution_id = str(uuid.uuid4())

class ReconWorker(Worker):
    def __init__(self, config: Config):
        super().__init__("recon", config)
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.current_task: Optional[asyncio.Task] = None
        self.function_map: Dict[str, Callable] = {}
        self.load_plugins()
        self.current_module = None
        self.current_target = None
        self.current_start_time = None

    async def setup_subscriptions(self):
        """Setup NATS subscriptions for the worker."""
        logger.debug("Setting up worker subscriptions...")
        try:
            async with self._subscription_lock:
                if self.state == WorkerState.PAUSED:
                    logger.debug("Worker is paused, skipping subscription setup")
                    return

                # Clean up existing subscriptions using parent class method
                await self._cleanup_subscriptions()

                subscription = await self.qm.subscribe(
                    subject="recon.input",
                    stream="RECON_INPUT",
                    durable_name="RECON_EXECUTE",
                    message_handler=self.message_handler,
                    batch_size=1,
                    queue_group="recon",
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.ALL,
                        'replay_policy': ReplayPolicy.INSTANT,
                        'max_deliver': 1,
                        'max_ack_pending': 1000,
                        'flow_control': False
                    },
                    pull_based=True
                )
                self._subscription = subscription
                self._sub_key = "RECON_INPUT:recon.input:RECON_EXECUTE"
                logger.debug(f"Subscribed to execute channel : {self._sub_key}")

                # Setup control subscriptions
                await self.qm.subscribe(
                    subject="worker.control.all",
                    stream="WORKER_CONTROL",
                    durable_name=f"CONTROL_ALL_{self.component_id}",
                    message_handler=self.control_message_handler,
                    batch_size=1,
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT
                    },
                    broadcast=True
                )

                await self.qm.subscribe(
                    subject="worker.control.all_recon",
                    stream="WORKER_CONTROL",
                    durable_name=f"CONTROL_ALL_RECON_{self.component_id}",
                    message_handler=self.control_message_handler,
                    batch_size=1,
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT
                    },
                    broadcast=True
                )

                await self.qm.subscribe(
                    subject=f"worker.control.{self.component_id}",
                    stream="WORKER_CONTROL",
                    durable_name=f"CONTROL_{self.component_id}",
                    message_handler=self.control_message_handler,
                    batch_size=1,
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT
                    },
                    broadcast=True
                )

        except Exception as e:
            logger.error(f"Error setting up worker subscriptions: {e}")
            raise

    async def start(self):
        """Start the worker with additional initialization."""
        await super().start()

    async def message_handler(self, raw_msg):
        """Handle incoming function execution messages."""
        # First check if we're already processing or paused
        if self.state == WorkerState.PAUSED:
            await raw_msg.nak()
            return

        # Try to acquire the processing lock
        if not await self._processing_lock.acquire():
            await raw_msg.nak()
            return

        try:
            # Double check state after acquiring lock
            if self.state != WorkerState.IDLE:
                await raw_msg.nak()
                return

            logger.debug(f"{self.component_id} received message: {raw_msg.data}")
            
            # Set state to busy before processing
            await self.set_state(WorkerState.BUSY, "parsing_incoming_job")
            msg = json.loads(raw_msg.data.decode())
            self._last_message_time = datetime.now(timezone.utc)

            # Parse message
            function_execution_request = FunctionExecutionRequest(
                program_id=msg.get('program_id'),
                function_name=msg.get('function_name'),
                params=msg.get('params'),
                force=msg.get("force", False)
            )
            logger.debug(f"Created function execution request: {function_execution_request}")
            if not function_execution_request.params.get('extra_params'):
                function_execution_request.params['extra_params'] = []
            elif not isinstance(function_execution_request.params['extra_params'], list):
                function_execution_request.params['extra_params'] = []

            # Check if we should execute this function
            if not function_execution_request.force and not await self._should_execute(function_execution_request):
                logger.info(f"JOB SKIPPED: {function_execution_request.function_name} : recently executed")
                await raw_msg.ack()
                return
            
            # Log execution start
            await self.db.log_reconworker_operation(
                execution_id=function_execution_request.execution_id,
                component_id=self.component_id,
                function_name=function_execution_request.function_name,
                program_id=function_execution_request.program_id,
                target=function_execution_request.params.get('target', 'unknown'),
                parameters=function_execution_request.params,
                status='started'
            )
            
            # Validation
            function_valid = await self.validate_function_execution_request(function_execution_request)
            if not function_valid:
                logger.info(f"JOB SKIPPED: {function_execution_request.function_name} : invalid function request")
                await self.db.log_reconworker_operation(
                    execution_id=function_execution_request.execution_id,
                    component_id=self.component_id,
                    function_name=function_execution_request.function_name,
                    program_id=function_execution_request.program_id,
                    target=function_execution_request.params.get('target', 'unknown'),
                    parameters=function_execution_request.params,
                    status='failed',
                    error_message='Invalid function request',
                    completed_at=datetime.now(timezone.utc)
                )
                await raw_msg.ack()
                return

            await self.set_state(WorkerState.BUSY, f"{function_execution_request.function_name}:{function_execution_request.params.get('target')}:{function_execution_request.execution_id}")
            # Execution
            logger.info(f"STARTING JOB: {function_execution_request.function_name} : {function_execution_request.params.get('target')} : {function_execution_request.execution_id}")
            self.current_task = asyncio.create_task(
                self.run_function_execution(function_execution_request)
            )
            await self.current_task
            self.current_task = None  # Reset the current task when done
                
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            logger.exception(e)
            if 'function_execution_request' in locals():
                await self.db.log_reconworker_operation(
                    execution_id=function_execution_request.execution_id,
                    component_id=self.component_id,
                    function_name=function_execution_request.function_name,
                    program_id=function_execution_request.program_id,
                    target=function_execution_request.params.get('target', 'unknown'),
                    parameters=function_execution_request.params,
                    status='failed',
                    error_message=str(e),
                    completed_at=datetime.now(timezone.utc)
                )
        finally:
            if not raw_msg._ackd:
                await raw_msg.ack()
            if self.state != WorkerState.PAUSED:
                await self.set_state(WorkerState.IDLE)
            self._processing_lock.release()

    async def validate_function_execution_request(self, function_execution_request: FunctionExecutionRequest) -> bool:
        """Validate the function execution request."""
        try:
            plugin_found = any(function_execution_request.function_name in key 
                             for key in self.function_map.keys())
            if not plugin_found:
                raise ValueError(f"Invalid function_name: {function_execution_request.function_name}")
            return plugin_found
        except Exception as e:
            logger.error(f"Error validating function request: {e}")
            return False
    
    @debug_trace
    async def run_function_execution(self, msg_data: FunctionExecutionRequest):
        """Execute the requested function."""
        result_count = 0
        
        try:
            async for result in self.execute_function(
                function_name=msg_data.function_name,
                params=msg_data.params,
                program_id=msg_data.program_id,
                execution_id=msg_data.execution_id
            ):
                if asyncio.current_task().cancelled():
                    await self.db.log_reconworker_operation(
                        execution_id=msg_data.execution_id,
                        component_id=self.component_id,
                        function_name=msg_data.function_name,
                        program_id=msg_data.program_id,
                        target=msg_data.params.get('target', 'unknown'),
                        parameters=msg_data.params,
                        status='failed',
                        error_message='Execution cancelled',
                        completed_at=datetime.now(timezone.utc)
                    )
                    return  # Exit the function to prevent further processing
                
                result_count += 1
                #logger.debug(f"Execution {msg_data.execution_id}: Result #{result_count}: {result}")
            logger.success(f"JOB COMPLETED: {msg_data.function_name} : {msg_data.params.get('target')} : {result_count} results")
            # Log successful completion
            await self.db.log_reconworker_operation(
                execution_id=msg_data.execution_id,
                component_id=self.component_id,
                function_name=msg_data.function_name,
                program_id=msg_data.program_id,
                target=msg_data.params.get('target', 'unknown'),
                parameters=msg_data.params,
                status='completed',
                completed_at=datetime.now(timezone.utc)
            )
                
        except asyncio.CancelledError:
            logger.warning(f"JOB CANCELLED: {msg_data.execution_id}:{msg_data.function_name} : {msg_data.params.get('target')}")
            return
        except Exception as e:
            logger.error(f"Error executing function {msg_data.execution_id}: {e}")
            await self.db.log_reconworker_operation(
                execution_id=msg_data.execution_id,
                component_id=self.component_id,
                function_name=msg_data.function_name,
                program_id=msg_data.program_id,
                target=msg_data.params.get('target', 'unknown'),
                parameters=msg_data.params,
                status='failed',
                error_message=str(e),
                completed_at=datetime.now(timezone.utc)
            )
            raise
            

    def load_plugins(self):
        """Dynamically load all recon plugins."""
        try:
            package = importlib.import_module('h3xrecon.plugins.plugins')
            logger.debug(f"Found plugin package at: {package.__path__}")
            
            # Walk through all subdirectories
            plugin_modules = []
            for finder, name, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
                if not name.endswith('.base'):  # Skip the base module
                    plugin_modules.append(name)
            
            logger.info(f"LOADED PLUGINS: {', '.join(p.split('.')[-1] for p in plugin_modules)}")
            
        except ModuleNotFoundError as e:
            logger.error(f"Failed to import 'plugins': {e}")
            return

        for module_name in plugin_modules:
            try:
                logger.debug(f"Attempting to load module: {module_name}")
                module = importlib.import_module(module_name)
                
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    
                    if not isinstance(attribute, type) or not issubclass(attribute, ReconPlugin) or attribute is ReconPlugin:
                       continue
                        
                    plugin_instance = attribute()
                    bound_method = plugin_instance.execute
                    self.function_map[plugin_instance.name] = bound_method
                    logger.debug(f"Loaded plugin: {plugin_instance.name} with timeout: {plugin_instance.timeout}s")
                
            except Exception as e:
                logger.error(f"Error loading plugin '{module_name}': {e}", exc_info=True)
        logger.debug(f"Current function_map: {[key for key in self.function_map.keys()]}")
    
    async def execute_function(self, function_name: str, params: Dict[str, Any], program_id: int, execution_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            # Update current execution info
            self.current_module = function_name
            self.current_target = params.get('target')
            self.current_start_time = datetime.now(timezone.utc)

            plugin = self.function_map.get(function_name)
            if not plugin:
                logger.error(f"Function {function_name} not found")
                raise ValueError(f"Function {function_name} not found")

            logger.debug(f"Running function {function_name} on {params.get('target')} ({execution_id})")
            
            try:
                async for result in plugin(params, program_id, execution_id, self.db):
                    output_data = {
                        "program_id": program_id,
                        "execution_id": execution_id,
                        "source": {
                            "function_name": function_name,
                            "params": params
                        },
                        "output": result,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # Yield the result first
                    yield output_data
                    
                    # Then attempt to publish it
                    try:
                        await self.qm.publish_message(
                            subject="parsing.input",
                            stream="PARSING_INPUT",
                            message=output_data
                        )
                        logger.info(f"SENT JOB OUTPUT: {function_name} : {params.get('target')}")
                    except StreamUnavailableError as e:
                        logger.warning(f"Stream locked, dropping message: {str(e)}")
                        continue  # Continue with the next result

            except Exception as e:
                logger.error(f"Error executing function {function_name}: {str(e)}")
                logger.exception(e)
                raise
            finally:
                logger.debug(f"Finished running {function_name} on {params.get('target')} ({execution_id})")

        except Exception as e:
            logger.error(f"Error executing function {function_name}: {str(e)}")
            logger.exception(e)
            raise

        finally:
            # Clear current execution info when done
            self.current_module = None
            self.current_target = None
            self.current_start_time = None


    async def stop(self):
        """Stop the worker with additional cleanup."""
        # Cancel all running tasks
        for execution_id, task in list(self.running_tasks.items()):
            task.cancel()
            logger.debug(f"Cancelled task with Execution ID: {execution_id}")
        await super().stop()

    async def _should_execute(self, request: FunctionExecutionRequest) -> bool:
        """
        Check if a function should be executed based on its last execution time.
        Returns True if the function should be executed, False otherwise.
        """
        try:
            # Handle extra_params specially if it exists as a list
            params = request.params
            if 'extra_params' in params and isinstance(params['extra_params'], list):
                extra_params_str = f"extra_params={sorted(params['extra_params'])}"
            else:
                # Create a sorted, filtered copy of params excluding certain keys
                extra_params = {k: v for k, v in sorted(params.items()) 
                              if k not in ['target', 'force'] and not k.startswith('--')}
                # Convert extra_params to a string representation
                extra_params_str = ':'.join(f"{k}={v}" for k, v in extra_params.items()) if extra_params else ''

            # Construct Redis key
            redis_key = f"{request.function_name}:{params.get('target', 'unknown')}:{extra_params_str}"
            
            # Get last execution time from Redis
            last_execution_time = self.redis_cache.get(redis_key)
            if not last_execution_time:
                return True

            # Parse the timestamp and ensure it's timezone-aware
            last_execution_time = datetime.fromisoformat(last_execution_time.decode().replace('Z', '+00:00'))
            if last_execution_time.tzinfo is None:
                last_execution_time = last_execution_time.replace(tzinfo=timezone.utc)
            
            current_time = datetime.now(timezone.utc)
            time_since_last = current_time - last_execution_time
            return time_since_last > self.execution_threshold

        except Exception as e:
            logger.error(f"Error checking execution history: {e}")
            # If there's an error checking history, allow execution
            return True

    async def _handle_killjob_command(self, msg: Dict[str, Any]):
        """Handle killjob command to cancel the running task."""
        try:
            if self.current_task:
                self.current_task.cancel()
                await self._send_control_response(command="killjob", status="task killed", success=True)
                logger.debug("Cancelled the current running task")
            else:
                logger.debug("No running task to cancel")
                await self._send_control_response(command="killjob", status="no running task", success=True)
        except Exception as e:
            logger.error(f"Error handling killjob command: {e}")
            await self._send_control_response(command="killjob", status="error", success=False)

async def main():
    config = Config()
    config.setup_logging()

    worker = ReconWorker(config)
    try:
        await worker.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await worker.stop()
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        sys.exit(1)

def run():
    asyncio.run(main())

if __name__ == "__main__":
    run()
