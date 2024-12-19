import asyncio
import socket
import sys
from loguru import logger
from h3xrecon.worker.executor import FunctionExecutor
from h3xrecon.core import QueueManager, DatabaseManager, Config, PreflightCheck
from h3xrecon.__about__ import __version__
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from dataclasses import dataclass
from typing import Dict, Any, Optional
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

import redis
import random
from enum import Enum

class ProcessorState(Enum):
    RUNNING = "running"
    PAUSED = "paused"

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

class Worker:
    def __init__(self, config: Config):
        self.worker_id = f"worker-{socket.gethostname()}-{random.randint(1000, 9999)}"
        self.config = config
        self.config.setup_logging()
        self.state = ProcessorState.RUNNING
        # Initialize components after preflight checks
        self.qm = None
        self.db = None
        self.redis_status = None
        self.redis_cache = None
        self.function_executor = None
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self._execution_semaphore = asyncio.Semaphore(1) 
        self._processing = False
        self._processing_lock = asyncio.Lock()
        self._health_check_task = None
        self._last_message_time = None
    
    
    
    async def initialize_components(self):
        """Initialize all worker components after successful preflight checks."""
        self.redis_status = redis.Redis(
            host=self.config.redis.host,
            port=self.config.redis.port,
            db=1,
            password=self.config.redis.password
        )
        self.redis_cache = redis.Redis(
            host=self.config.redis.host,
            port=self.config.redis.port,
            db=self.config.redis.db,
            password=self.config.redis.password
        )
        self.qm = QueueManager(client_name=self.worker_id, config=self.config.nats)
        self.db = DatabaseManager()
        self.function_executor = FunctionExecutor(
            worker_id=self.worker_id,
            qm=self.qm,
            db=self.db,
            config=self.config,
            redis_status=self.redis_status
        )
    
    def set_status(self, status: str):
        self.redis_status.set(self.worker_id, status)
    
    async def start(self):
        logger.info(f"Starting Worker (Worker ID: {self.worker_id}) version {__version__}...")
        try:
            # Run preflight checks
            preflight = PreflightCheck(self.config, f"worker-{self.worker_id}")
            if not await preflight.run_checks():
                logger.error("Preflight checks failed. Exiting.")
                sys.exit(1)
            
            # Initialize components
            await self.initialize_components()

            # Start health check
            self._health_check_task = asyncio.create_task(self._health_check())

            # Subscribe to control messages with updated configuration
            await self.qm.subscribe(
                subject="function.control",
                stream="FUNCTION_CONTROL",
                durable_name=f"CONTROL_{self.worker_id}",
                message_handler=self.control_message_handler,
                batch_size=1,
                consumer_config={
                    'ack_policy': AckPolicy.EXPLICIT,
                    'deliver_policy': DeliverPolicy.NEW,
                    'replay_policy': ReplayPolicy.INSTANT
                },
                broadcast=True
            )

            # Subscribe to execute messages with AckPolicy.EXPLICIT
            await self.qm.subscribe(
                subject="function.execute",
                stream="FUNCTION_EXECUTE",
                durable_name=f"EXECUTE_WORKER",
                message_handler=self.message_handler,
                batch_size=1,
                consumer_config={
                    'ack_policy': AckPolicy.EXPLICIT,  # Correct attribute
                    'deliver_policy': DeliverPolicy.ALL,
                    'replay_policy': ReplayPolicy.INSTANT
                },
                queue_group="workers",
                broadcast=False
            )

            logger.info(f"Worker {self.worker_id} started and listening for messages...")
        except AttributeError as ae:
            logger.error(f"Attribute error during startup: {ae}")
            logger.exception(ae)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to start worker: {e}")
            logger.exception(e)
            sys.exit(1)
            logger.exception(e)
            sys.exit(1)

    async def control_message_handler(self, msg):
        logger.debug("Entered control_message_handler")
        try:
            messages = [msg] if isinstance(msg, dict) else msg

            for message in messages:
                try:
                    logger.debug(f"Received control message: {message}")
                    command = message.get('command')
                    execution_id = message.get('execution_id')
                    target_worker_id = message.get('target_worker_id')
                    target = message.get('target', 'all')
                    
                    # If the message is targeted to a specific worker and it's not this worker, skip
                    if target_worker_id and target_worker_id != self.worker_id:
                        logger.debug(f"Control message targeted to worker {target_worker_id}, skipping.")
                        continue

                    # Skip messages not meant for workers
                    if target not in ["all", "worker"]:
                        logger.debug(f"Control message targeted to {target}, skipping.")
                        if hasattr(msg, 'ack'):
                            await msg.ack()
                        continue

                    # Handle pause/unpause commands
                    if command == "pause":
                        logger.info("Received pause command")
                        self.state = ProcessorState.PAUSED
                        self.set_status("paused")
                        # Send acknowledgment
                        await self.qm.publish_message(
                            subject="function.control.response",
                            stream="FUNCTION_CONTROL_RESPONSE",
                            message={
                                "processor_id": self.worker_id,
                                "type": "worker",
                                "status": "paused",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                    
                    elif command == "unpause":
                        logger.info("Received unpause command")
                        self.state = ProcessorState.RUNNING
                        self.set_status("idle")
                        # Send acknowledgment
                        await self.qm.publish_message(
                            subject="function.control.response",
                            stream="FUNCTION_CONTROL_RESPONSE",
                            message={
                                "processor_id": self.worker_id,
                                "type": "worker",
                                "status": "running",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                    
                    elif command == 'killjob':
                        if self.running_tasks:
                            # Cancel the first running task
                            execution_id = next(iter(self.running_tasks))
                            task = self.running_tasks.get(execution_id)
                            if task:
                                logger.debug(f"Killing job with Execution ID: {execution_id}")
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    logger.info(f"Successfully cancelled task {execution_id}")
                    
                    elif command == 'stop' and execution_id:
                        task = self.running_tasks.get(execution_id)
                        if task:
                            logger.debug(f"Stopping job with Execution ID: {execution_id}")
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                logger.info(f"Successfully cancelled task {execution_id}")
                        else:
                            logger.warning(f"No running task found with Execution ID: {execution_id}")
                    else:
                        logger.warning(f"Received unknown control command or missing execution_id: {message}")

                    # Acknowledge the message after successful processing
                    if hasattr(msg, 'ack'):
                        await msg.ack()

                except Exception as processing_error:
                    logger.error(f"Error processing individual control message: {processing_error}")
                    logger.exception(processing_error)
                    # Decide whether to acknowledge based on error type
                    if hasattr(msg, 'ack'):
                        await msg.ack()
                    continue

        except Exception as batch_error:
            logger.error(f"Error processing control message batch: {batch_error}")
            logger.exception(batch_error)
            if hasattr(msg, 'ack'):
                await msg.ack()
    
    async def should_execute(self, request: FunctionExecutionRequest) -> bool:
        """
        Determine whether a function should be executed based on the last execution time.

        Args:
            request: FunctionExecutionRequest object containing execution details

        Returns:
            bool: True if the function should be executed, False otherwise
        """
        data = request
        redis_key = f"{data.function_name}:{data.params.get('target')}"
        last_execution_bytes = self.redis_cache.get(redis_key)
        logger.debug(f"Raw last execution from Redis for '{request.function_name}' on target '{request.params.get('target')}': {last_execution_bytes}")

        if last_execution_bytes:
            try:
                # Decode bytes to string and parse to datetime
                last_execution_str = last_execution_bytes.decode('utf-8')
                last_execution = datetime.fromisoformat(last_execution_str)
                
                # Make sure last_execution_time is offset-aware
                if last_execution.tzinfo is None:
                    logger.warning("last_execution_time is offset-naive. Making it offset-aware (UTC).")
                    last_execution = last_execution.replace(tzinfo=timezone.utc)

                current_time = datetime.now(timezone.utc)
                time_since_last_execution = current_time - last_execution
                logger.debug(f"Time since last execution: {time_since_last_execution}")

                if time_since_last_execution < self.execution_threshold:
                    logger.info(f"Execution threshold not met for function '{request.function_name}' on target '{request.params.get('target')}'. Skipping execution.")
                    return False
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error parsing last execution time from Redis: {e}. Proceeding with execution.")
                return True
        else:
            logger.info(f"No previous execution found for function '{request.function_name}' on target '{request.params.get('target')}'. Proceeding with execution.")

        return True
    
    async def validate_function_execution_request(self, function_execution_request: FunctionExecutionRequest) -> bool:
        # Validate function_name is a valid plugin
        try:
            # Dynamically import plugins to check if the function_name is valid
            plugin_found = False
            
            # Check if the function name exists in the function map keys
            plugin_found = any(function_execution_request.function_name in key for key in self.function_executor.function_map.keys())
            
            if not plugin_found:
                logger.debug(f"Invalid function_name: {function_execution_request.function_name}. No matching plugin found in {list(self.function_executor.function_map.keys())}")
                raise ValueError(f"Invalid function_name: {function_execution_request.function_name}. No matching plugin found.")
        
        except Exception as e:
            raise ValueError(f"Error validating function_name: {str(e)}")
        
        # Validate program_name exists in the database
        try:
            program_name = await self.db.get_program_name(function_execution_request.program_id)
            if not program_name:
                raise ValueError(f"Invalid program_id: {function_execution_request.program_id}. Program not found in database.")
        
        except Exception as e:
            raise ValueError(f"Error validating program_name: {str(e)}")

    async def message_handler(self, msg):
        if self.state == ProcessorState.PAUSED:
            logger.debug("Worker is paused, skipping message")
            if hasattr(msg, 'ack'):
                await msg.ack()
            return

        self._last_message_time = datetime.now(timezone.utc)
        logger.debug("Entered message_handler")
        processing_lock_acquired = False
        
        try:
            # Try to acquire the processing lock
            async with self._processing_lock:
                if self._processing:
                    logger.info("Already processing a job, skipping new message")
                    # Make sure to acknowledge the message so it's not stuck
                    if hasattr(msg, 'ack'):
                        await msg.ack()
                    return
                self._processing = True
                processing_lock_acquired = True

            try:
                # Parse message
                function_execution_request = FunctionExecutionRequest(
                    program_id=msg.get('program_id'),
                    function_name=msg.get('function'),
                    params=msg.get('params'),
                    force=msg.get("force", False)
                )
                
                # Validation
                await self.validate_function_execution_request(function_execution_request)
                if not function_execution_request.force:
                    if not await self.should_execute(function_execution_request):
                        logger.info(f"Skipping execution: {function_execution_request.function_name} on {function_execution_request.params.get('target')} executed recently.")
                        return

                # Create and track the task
                task = asyncio.create_task(
                    self.run_function_execution(function_execution_request)
                )
                self.running_tasks[function_execution_request.execution_id] = task

                # Add callback to handle task completion
                task.add_done_callback(
                    lambda t, eid=function_execution_request.execution_id: self.task_done_callback(t, eid)
                )

                try:
                    # Changed from asyncio.shield to direct await
                    await task
                except asyncio.CancelledError:
                    logger.info(f"Task execution cancelled for {function_execution_request.execution_id}")
                    # Don't re-raise the cancellation
                    pass

            except Exception as processing_error:
                logger.error(f"Error processing execute message: {processing_error}")
                logger.exception(processing_error)
            finally:
                # Always acknowledge the message
                if hasattr(msg, 'ack'):
                    await msg.ack()

        finally:
            # Always release the processing lock
            if processing_lock_acquired:
                async with self._processing_lock:
                    self._processing = False
                    logger.debug("Released processing lock")
            
            logger.debug("Exited message_handler")

    def task_done_callback(self, task: asyncio.Task, execution_id: str):
        """
        Callback function to handle task completion.
        """
        try:
            exception = task.exception()
            if exception:
                logger.error(f"Task {execution_id} encountered an exception: {exception}")
            else:
                logger.info(f"Task {execution_id} completed successfully.")
        except asyncio.CancelledError:
            logger.info(f"Task {execution_id} was cancelled.")
        finally:
            # Remove the task from running_tasks regardless of outcome
            self.running_tasks.pop(execution_id, None)

    async def run_function_execution(self, msg_data: FunctionExecutionRequest):
        logger.info(f"Starting execution of function '{msg_data.function_name}' with Execution ID: {msg_data.execution_id}")
        try:
            execution_id = msg_data.execution_id
            # Add debug logging to track results
            result_count = 0
            async for result in self.function_executor.execute_function(
                function_name=msg_data.function_name,
                params=msg_data.params,
                program_id=msg_data.program_id,
                execution_id=execution_id
            ):
                result_count += 1
                logger.debug(f"Execution {execution_id}: Received result #{result_count}: {result}")
                # Make sure we're actually getting results before moving on
                if not result:
                    logger.warning(f"Received empty result from {msg_data.function_name}")
                    continue
        except asyncio.CancelledError:
            logger.info(f"Execution {execution_id} was cancelled.")
            raise
        except Exception as e:
            logger.error(f"Error executing function {execution_id}: {e}")
            logger.exception(e)
            raise
        finally:
            logger.info(f"Finished execution of function '{msg_data.function_name}' with Execution ID: {msg_data.execution_id}. Total results: {result_count}")

    async def stop(self):
        logger.info("Shutting down...")
        # Cancel all running tasks
        for execution_id, task in list(self.running_tasks.items()):
            task.cancel()
            logger.info(f"Cancelled task with Execution ID: {execution_id}")
        await self.qm.disconnect()
        logger.info("Worker shutdown complete")

    async def _health_check(self):
        """Monitor worker health and subscription status."""
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                if self._last_message_time:
                    time_since_last_message = current_time - self._last_message_time
                    if time_since_last_message > timedelta(minutes=5):  # Adjust timeout as needed
                        logger.warning(f"No messages received for {time_since_last_message}. Reconnecting subscriptions...")
                        await self._reconnect_subscriptions()
                
                # Check if we're still connected to NATS
                if not self.qm.nc.is_connected:
                    logger.error("NATS connection lost. Attempting to reconnect...")
                    await self.qm.ensure_connected()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                await asyncio.sleep(5)
    
    async def _reconnect_subscriptions(self):
        """Reconnect all subscriptions."""
        try:
            logger.info("Reconnecting subscriptions...")
            # Resubscribe to execute messages
            await self.qm.subscribe(
                subject="function.execute",
                stream="FUNCTION_EXECUTE",
                durable_name=f"EXECUTE_{self.worker_id}",
                message_handler=self.message_handler,
                batch_size=1,
                consumer_config={
                    'ack_policy': AckPolicy.EXPLICIT,
                    'deliver_policy': DeliverPolicy.ALL,
                    'replay_policy': ReplayPolicy.INSTANT
                },
                broadcast=False
            )
            logger.info("Successfully reconnected subscriptions")
        except Exception as e:
            logger.error(f"Error reconnecting subscriptions: {e}")

async def main():
    try:
        # Load configuration
        config = Config()
        config.setup_logging()
        logger.info(f"Starting H3XRecon worker... (v{__version__})")

        # Initialize and start worker
        worker = Worker(config)
        
        try:
            await worker.start()
            
            # Keep the worker running
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Shutting down worker...")
            await worker.stop()
            
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        sys.exit(1)
    finally:
        if hasattr(worker, 'redis_status'):
            worker.redis_status.delete(worker.worker_id)
        logger.info("Worker shutdown complete")

def run():
    asyncio.run(main())

if __name__ == "__main__":
    run()