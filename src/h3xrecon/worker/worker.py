import asyncio
import sys
from loguru import logger
from h3xrecon.core.component import ReconComponent, ProcessorState
from h3xrecon.worker.executor import FunctionExecutor
from h3xrecon.core import Config
from h3xrecon.__about__ import __version__
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from dataclasses import dataclass
from typing import Dict, Any, Optional
import uuid
from datetime import datetime, timezone, timedelta
import json

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

class Worker(ReconComponent):
    def __init__(self, config: Config):
        super().__init__("worker", config)
        self.function_executor = None
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.current_task: Optional[asyncio.Task] = None  # Track the currently running task

    async def setup_subscriptions(self):
        """Setup NATS subscriptions for the worker."""
        logger.debug("Setting up worker subscriptions...")
        try:
            async with self._subscription_lock:
                if self.state == ProcessorState.PAUSED:
                    logger.debug("Worker is paused, skipping subscription setup")
                    return

                # Clean up existing subscriptions using parent class method
                await self._cleanup_subscriptions()

                subscription = await self.qm.subscribe(
                    subject="function.execute",
                    stream="FUNCTION_EXECUTE",
                    durable_name="WORKERS_EXECUTE",
                    message_handler=self.message_handler,
                    batch_size=1,
                    queue_group="workers",
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
                self._sub_key = f"FUNCTION_EXECUTE:function.execute:WORKERS_EXECUTE"
                logger.info("Successfully subscribed to execute channel")

                # Setup control subscriptions
                await self.qm.subscribe(
                    subject="function.control.all",
                    stream="FUNCTION_CONTROL",
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
                    subject="function.control.all_worker",
                    stream="FUNCTION_CONTROL",
                    durable_name=f"CONTROL_ALL_WORKER_{self.component_id}",
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
                    subject=f"function.control.{self.component_id}",
                    stream="FUNCTION_CONTROL",
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
        self.function_executor = FunctionExecutor(
            worker_id=self.component_id,
            qm=self.qm,
            db=self.db,
            config=self.config,
            redis_status=self.redis_status
        )

    async def message_handler(self, raw_msg):
        """Handle incoming function execution messages."""
        logger.debug(f"Worker {self.component_id} received message: {raw_msg.data}")
        if self.state == ProcessorState.PAUSED:
            await raw_msg.nak()
            return
        try:
            self.state = ProcessorState.BUSY
            msg = json.loads(raw_msg.data.decode())
            self._last_message_time = datetime.now(timezone.utc)

            # Parse message
            function_execution_request = FunctionExecutionRequest(
                program_id=msg.get('program_id'),
                function_name=msg.get('function'),
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
                logger.info(f"Skipping execution of {function_execution_request.function_name} - recently executed")
                await raw_msg.ack()
                return

            # Log execution start
            await self.db.log_worker_execution(
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
                logger.info(f"Skipping execution: {function_execution_request.function_name}")
                await self.db.log_worker_execution(
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

            await self.set_status(f"busy:{function_execution_request.function_name}:{function_execution_request.params.get('target')}")
            # Execution
            self.current_task = asyncio.create_task(
                self.run_function_execution(function_execution_request)
            )
            await self.current_task
            self.current_task = None  # Reset the current task when done
                
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            logger.exception(e)
            if 'function_execution_request' in locals():
                await self.db.log_worker_execution(
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
            await self.set_status("idle")

    async def validate_function_execution_request(self, function_execution_request: FunctionExecutionRequest) -> bool:
        """Validate the function execution request."""
        try:
            plugin_found = any(function_execution_request.function_name in key 
                             for key in self.function_executor.function_map.keys())
            if not plugin_found:
                raise ValueError(f"Invalid function_name: {function_execution_request.function_name}")
            return plugin_found
        except Exception as e:
            logger.error(f"Error validating function request: {e}")
            return False

    async def run_function_execution(self, msg_data: FunctionExecutionRequest):
        """Execute the requested function."""
        logger.info(f"Starting execution of function '{msg_data.function_name}' with Execution ID: {msg_data.execution_id}")
        result_count = 0
        
        try:
            async for result in self.function_executor.execute_function(
                function_name=msg_data.function_name,
                params=msg_data.params,
                program_id=msg_data.program_id,
                execution_id=msg_data.execution_id
            ):
                if asyncio.current_task().cancelled():
                    logger.info(f"Execution {msg_data.execution_id} was cancelled")
                    await self.db.log_worker_execution(
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
                logger.debug(f"Execution {msg_data.execution_id}: Result #{result_count}: {result}")
                
            # Log successful completion
            await self.db.log_worker_execution(
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
            logger.info(f"Execution {msg_data.execution_id} was cancelled.")
            # Handle cancellation without affecting the message processing loop
            return
        except Exception as e:
            logger.error(f"Error executing function {msg_data.execution_id}: {e}")
            await self.db.log_worker_execution(
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
        finally:
            logger.info(f"Finished execution of '{msg_data.function_name}'. Total results: {result_count}")
            await self.set_status("idle")

    async def stop(self):
        """Stop the worker with additional cleanup."""
        # Cancel all running tasks
        for execution_id, task in list(self.running_tasks.items()):
            task.cancel()
            logger.info(f"Cancelled task with Execution ID: {execution_id}")
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
        if self.current_task:
            self.current_task.cancel()
            await self._send_control_response("killjob", "killed", True)
            logger.info("Cancelled the current running task")
        else:
            logger.warning("No running task to cancel")

async def main():
    config = Config()
    config.setup_logging()
    logger.info(f"Starting H3XRecon worker... (v{__version__})")

    worker = Worker(config)
    try:
        await worker.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")
        await worker.stop()
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        sys.exit(1)

def run():
    asyncio.run(main())

if __name__ == "__main__":
    run()
