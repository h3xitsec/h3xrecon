import asyncio
import sys
from loguru import logger
from h3xrecon.core.worker import Worker, WorkerState
from h3xrecon.core import Config
from h3xrecon.core.queue import StreamUnavailableError
from h3xrecon.core.utils import check_last_execution
from h3xrecon.core.models import ReconJobRequest
from h3xrecon.plugins import ReconPlugin
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from h3xrecon.core.utils import debug_trace
from typing import Dict, Any, Optional, Callable, AsyncGenerator
from datetime import datetime, timezone, timedelta
from time import sleep
import json
import importlib
import pkgutil

class ReconWorker(Worker):
    def __init__(self, config: Config = Config()):
        super().__init__("recon", config)
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.current_task: Optional[asyncio.Task] = None
        self.current_process: Optional[asyncio.subprocess.Process] = None  # Track current subprocess
        self.function_map: Dict[str, Callable] = {}
        self.function_input_validator: Dict[str, Callable] = {}
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
                # RECON_INPUT: Job requests queue
                subscription = await self.qm.subscribe(
                    subject="recon.input.>",
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
                #logger.debug(f"Subscribed to execute channel : {self._sub_key}")

                # Base control subscription settings
                base_control_subscription_settings = {
                    "message_handler": self.control_message_handler,
                    "stream": "WORKER_CONTROL",
                    "batch_size": 1,
                    "consumer_config": {
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT
                    },
                    "broadcast": True
                }
                # Setup control subscriptions
                await self.qm.subscribe(
                    subject="worker.control.all",
                    durable_name=f"CONTROL_ALL_{self.component_id}",
                    **base_control_subscription_settings
                )

                await self.qm.subscribe(
                    subject="worker.control.all_recon",
                    durable_name=f"CONTROL_ALL_RECON_{self.component_id}",
                    **base_control_subscription_settings
                )

                await self.qm.subscribe(
                    subject=f"worker.control.{self.component_id}",
                    durable_name=f"CONTROL_{self.component_id}",
                    **base_control_subscription_settings
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

            logger.info(f"RECEIVED JOB REQUEST: {raw_msg.data}")
            
            # Set state to busy before processing
            await self.set_state(WorkerState.BUSY, "parsing_incoming_job")
            # Deal with batch jobs messages
            # If the message is a single job, wrap it in a list then loop through it
            msg_data = json.loads(raw_msg.data.decode())
            if isinstance(msg_data, dict):
                msg_data = [msg_data]
            self._last_message_time = datetime.now(timezone.utc)
            for msg in msg_data:
                # Parse message
                recon_job_request = ReconJobRequest(**msg)
                if not recon_job_request.params.get('extra_params'):
                    recon_job_request.params['extra_params'] = []
                elif not isinstance(recon_job_request.params['extra_params'], list):
                    recon_job_request.params['extra_params'] = []

                # Validation
                function_valid = await self.validate_recon_job_request(recon_job_request)
                if not function_valid:
                    logger.info(f"JOB SKIPPED: {recon_job_request.function_name} : invalid function request")
                    if recon_job_request.response_id or recon_job_request.debug_id:
                        response_subject_id = recon_job_request.response_id
                        sleep(5)
                        await self._send_jobrequest_response(recon_job_request.execution_id, response_subject_id, status="error: invalid function request")
                    # await self.db.log_reconworker_operation(
                    #     execution_id=recon_job_request.execution_id,
                    #     component_id=self.component_id,
                    #     function_name=recon_job_request.function_name,
                    #     program_id=recon_job_request.program_id,
                    #     target=recon_job_request.params.get('target', 'unknown'),
                    #     parameters=recon_job_request.params,
                    #     status='failed',
                    #     error_message='Invalid function request',
                    #     completed_at=datetime.now(timezone.utc)
                    # )
                    await raw_msg.ack()
                    return
                
                # Job Execution
                self.current_task = asyncio.create_task(
                    self.run_function_execution(recon_job_request)
                )
                if recon_job_request.response_id or recon_job_request.debug_id:
                    response_subject_id = recon_job_request.response_id
                    await self._send_jobrequest_response(recon_job_request.execution_id, response_subject_id, status="started")
                await self.current_task
                self.current_task = None  # Reset the current task when done
                
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            #logger.exception(e)
            # if 'recon_job_request' in locals():
            #     await self.db.log_reconworker_operation(
            #         execution_id=recon_job_request.execution_id,
            #         component_id=self.component_id,
            #         function_name=recon_job_request.function_name,
            #         program_id=recon_job_request.program_id,
            #         target=recon_job_request.params.get('target', 'unknown'),
            #         parameters=recon_job_request.params,
            #         status='failed',
            #         error_message=str(e),
            #         completed_at=datetime.now(timezone.utc)
            #     )
        finally:
            if not raw_msg._ackd:
                await raw_msg.ack()
            if self.state != WorkerState.PAUSED:
                await self.set_state(WorkerState.IDLE)
            self._processing_lock.release()

    async def validate_recon_job_request(self, recon_job_request: ReconJobRequest) -> bool:
        """Validate the function execution request."""
        try:
            plugin_found = any(recon_job_request.function_name in key 
                             for key in self.function_map.keys())
            if not plugin_found:
                raise ValueError(f"Invalid function_name: {recon_job_request.function_name}")
            if self.function_input_validator.get(recon_job_request.function_name, None):
                return await self.function_input_validator[recon_job_request.function_name](recon_job_request.params)
            return True
        except Exception as e:
            logger.error(f"Error validating function request: {e}")
            return False
    
    @debug_trace
    async def run_function_execution(self, msg_data: ReconJobRequest):
        """Execute the requested function."""
        
        try:
            async for result in self.execute_function(msg_data):
                if asyncio.current_task().cancelled():
                    # await self.db.log_reconworker_operation(
                    #     execution_id=msg_data.execution_id,
                    #     component_id=self.component_id,
                    #     function_name=msg_data.function_name,
                    #     program_id=msg_data.program_id,
                    #     target=msg_data.params.get('target', 'unknown'),
                    #     parameters=msg_data.params,
                    #     status='failed',
                    #     error_message='Execution cancelled',
                    #     completed_at=datetime.now(timezone.utc)
                    # )
                    return  # Exit the function to prevent further processing
                
                #logger.debug(f"Execution {msg_data.execution_id}: Result #{result_count}: {result}")
            #logger.success(f"JOB COMPLETED: {msg_data.function_name} : {msg_data.params.get('target')} : {result_count} results")
            # Log successful completion
            # await self.db.log_reconworker_operation(
            #     execution_id=msg_data.execution_id,
            #     component_id=self.component_id,
            #     function_name=msg_data.function_name,
            #     program_id=msg_data.program_id,
            #     target=msg_data.params.get('target', 'unknown'),
            #     parameters=msg_data.params,
            #     status='completed',
            #     completed_at=datetime.now(timezone.utc)
            # )
                
        except asyncio.CancelledError:
            logger.warning(f"JOB CANCELLED: {msg_data.execution_id}:{msg_data.function_name} : {msg_data.params.get('target')}")
            return
        except Exception as e:
            logger.error(f"Error executing function {msg_data.execution_id}: {e}")
            # await self.db.log_reconworker_operation(
            #     execution_id=msg_data.execution_id,
            #     component_id=self.component_id,
            #     function_name=msg_data.function_name,
            #     program_id=msg_data.program_id,
            #     target=msg_data.params.get('target', 'unknown'),
            #     parameters=msg_data.params,
            #     status='failed',
            #     error_message=str(e),
            #     completed_at=datetime.now(timezone.utc)
            # )
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
                #logger.debug(f"Attempting to load module: {module_name}")
                module = importlib.import_module(module_name)
                
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    
                    if not isinstance(attribute, type) or not issubclass(attribute, ReconPlugin) or attribute is ReconPlugin:
                       continue
                        
                    plugin_instance = attribute()
                    bound_method = plugin_instance.execute
                    self.function_map[plugin_instance.name] = {
                        'execute': bound_method,
                        'format_input': plugin_instance.format_input,
                        'format_targets': plugin_instance.format_targets,
                        'timeout': plugin_instance.timeout,
                        'is_valid_input': plugin_instance.is_valid_input,
                    }
                    logger.debug(f"Loaded plugin: {plugin_instance.name} with timeout: {plugin_instance.timeout}s")
                
            except Exception as e:
                logger.error(f"Error loading plugin '{module_name}': {e}", exc_info=True)
        #logger.debug(f"Current function_map: {[key for key in self.function_map.keys()]}")

    async def execute_function(self, recon_job_request: ReconJobRequest) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            # Update current execution info
            self.current_module = recon_job_request.function_name
            self.current_target = recon_job_request.params.get('target')
            self.current_start_time = datetime.now(timezone.utc)
            self.current_process = None  # Reset current process

            plugin = self.function_map.get(recon_job_request.function_name)
            if not plugin:
                logger.error(f"Function {recon_job_request.function_name} not found")
                raise ValueError(f"Function {recon_job_request.function_name} not found")

            # Get timeout from request or plugin default
            timeout = recon_job_request.params.get('timeout', plugin['timeout'])
            #logger.debug(f"Using timeout of {timeout} seconds for {recon_job_request.function_name}")

            # Format input
            if recon_job_request.function_name != "sleep":
                _fixed_targets = await plugin['format_targets'](recon_job_request.params['target'])
                logger.debug(f"FIXED TARGETS: {_fixed_targets}")
            else:
                _fixed_targets = [recon_job_request.params['target']]
            result_count = 0
            for _target in _fixed_targets:
                # Create a new params dictionary with the updated target
                new_recon_job_request = ReconJobRequest(
                    program_id=recon_job_request.program_id,
                    function_name=recon_job_request.function_name,
                    params={
                        **recon_job_request.params,
                        'target': _target
                    },
                    force=recon_job_request.force,
                    execution_id=recon_job_request.execution_id
                )
                # Update current target
                self.current_target = _target
                # Validate input
                if plugin.get('is_valid_input', None):
                    if not await plugin['is_valid_input'](new_recon_job_request.params):
                        logger.info(f"JOB SKIPPED: {recon_job_request.function_name} : invalid input")
                        if recon_job_request.response_id or recon_job_request.debug_id:
                            response_subject_id = recon_job_request.response_id
                            await self._send_jobrequest_response(recon_job_request.execution_id, response_subject_id, status="error: invalid input")
                        return
                
                # Check if we should execute this function
                if not recon_job_request.force and not await self._should_execute(new_recon_job_request):
                    logger.info(f"JOB SKIPPED: {recon_job_request.function_name} : recently executed")
                    if recon_job_request.response_id or recon_job_request.debug_id:
                        response_subject_id = recon_job_request.response_id
                        await self._send_jobrequest_response(recon_job_request.execution_id, response_subject_id, status="skipped: executed recently")
                    return
                
                # Log execution start
                # await self.db.log_reconworker_operation(
                #     execution_id=recon_job_request.execution_id,
                #     component_id=self.component_id,
                #     function_name=recon_job_request.function_name,
                #     program_id=recon_job_request.program_id,
                #     target=new_recon_job_request.params.get('target', 'unknown'),
                #     parameters=new_recon_job_request.params,
                #     status='started'
                # )
                logger.debug(f"Running function {recon_job_request.function_name} on {new_recon_job_request.params.get('target')} ({recon_job_request.execution_id})")
                await self.set_state(WorkerState.BUSY, f"{recon_job_request.function_name}:{new_recon_job_request.params.get('target')}:{recon_job_request.execution_id}")
                try:
                    # Pass self as worker to the plugin's execute methodl
                    execution = plugin['execute'](new_recon_job_request.params, recon_job_request.program_id, recon_job_request.execution_id, self.db, self.qm)
                    if recon_job_request.debug_id:
                        debug_results = []
                    while True:
                        try:
                            result = await asyncio.wait_for(
                                execution.__anext__(),
                                timeout=timeout
                            )
                            if result:
                                output_data = {
                                    "program_id": recon_job_request.program_id,
                                    "execution_id": recon_job_request.execution_id,
                                    "trigger_new_jobs": recon_job_request.trigger_new_jobs,
                                    "source": {
                                        "function_name": recon_job_request.function_name,
                                        "params": new_recon_job_request.params,
                                        "force": recon_job_request.force
                                    },
                                    "data": result,
                                    "timestamp": datetime.now().isoformat()
                                }
                                logger.debug(f"OUTPUT DATA: {output_data}")
                                # Yield the result first
                                yield output_data
                                try:
                                    if recon_job_request.debug_id:
                                        debug_results.append(result)
                                    else:
                                        await self.qm.publish_message(
                                            subject="parsing.input",
                                            stream="PARSING_INPUT",
                                            message=output_data
                                        )
                                    logger.info(f"SENT JOB OUTPUT: {recon_job_request.function_name} : {new_recon_job_request.params.get('target')} : {output_data}")
                                    result_count += 1
                                except StreamUnavailableError as e:
                                    logger.warning(f"Stream locked, dropping message: {str(e)}")
                                    continue  # Continue with the next result
                        except StopAsyncIteration:
                            break
                    # Send end of job message
                    if recon_job_request.debug_id:
                        await self._send_jobrequest_response(recon_job_request.execution_id, recon_job_request.debug_id, status=debug_results)
                    elif recon_job_request.response_id:
                        message = {
                            "program_id": recon_job_request.program_id,
                            "execution_id": recon_job_request.execution_id,
                            "trigger_new_jobs": recon_job_request.trigger_new_jobs,
                            "response_id": recon_job_request.response_id,
                            "source": {
                                "function_name": recon_job_request.function_name,
                                "params": new_recon_job_request.params,
                                "force": recon_job_request.force
                            },
                            "data": {"job_completed": True},
                            "timestamp": datetime.now().isoformat()
                        }
                        logger.debug(f"Sending end of job message: {message}")
                        await self.qm.publish_message(
                            subject="parsing.input",
                            stream="PARSING_INPUT",
                            message=message
                        )
                except asyncio.TimeoutError:
                    logger.error(f"Function {recon_job_request.function_name} timed out after {timeout} seconds")
                    # Kill any running subprocess
                    if self.current_process:
                        try:
                            import signal
                            import os
                            # Get the process group ID and kill it
                            try:
                                os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            except Exception as e:
                                logger.error(f"Error killing process group: {e}")
                                # Fallback to killing just the process
                                try:
                                    self.current_process.kill()
                                except:
                                    pass
                            
                            await self.current_process.wait()
                        except Exception as e:
                            logger.error(f"Error killing subprocess: {e}")
                        finally:
                            self.current_process = None
                    #raise
                except Exception as e:
                    logger.error(f"Error executing function {recon_job_request.function_name}: {str(e)}")
                    #logger.exception(e)
                    raise
                finally:
                    logger.success(f"JOB COMPLETED: {recon_job_request.function_name} : {new_recon_job_request.params.get('target')} : {result_count} results")

        except Exception as e:
            logger.error(f"Error executing function {recon_job_request.function_name}: {str(e)}")
            #logger.exception(e)
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

    async def _should_execute(self, request: ReconJobRequest) -> bool:
        """
        Check if a function should be executed based on its last execution time.
        Returns True if the function should be executed, False otherwise.
        """
        try:
            # Never check last execution for sleep plugin
            if request.function_name == "sleep":
                return True
            time_since_last = check_last_execution(request.function_name, request.params, self.redis_cache)
            return time_since_last > self.execution_threshold if time_since_last else True

        except Exception as e:
            logger.error(f"Error checking execution history: {e}")
            # If there's an error checking history, allow execution
            return True

    async def _handle_killjob_command(self, msg: Dict[str, Any]):
        """Handle killjob command to cancel the running task and kill any running subprocess."""
        try:
            if self.current_task:
                # First kill any running subprocess
                if self.current_process:
                    try:
                        import signal
                        import os
                        # Get the process group ID and kill it
                        try:
                            os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        except Exception as e:
                            logger.error(f"Error killing process group: {e}")
                            # Fallback to killing just the process
                            try:
                                self.current_process.kill()
                            except:
                                pass
                        
                        await self.current_process.wait()
                    except Exception as e:
                        logger.error(f"Error killing subprocess: {e}")
                    finally:
                        self.current_process = None

                # Then cancel the asyncio task
                self.current_task.cancel()
                await self._send_control_response(command="killjob", status="task killed", success=True)
                logger.debug("Cancelled the current running task and killed subprocess")
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
