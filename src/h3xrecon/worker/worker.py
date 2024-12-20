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
import psutil
import platform
import json

class ProcessorState(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    BUSY = "busy"

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
        self.qm = None  # Main queue manager for execute messages
        self.control_qm = None  # Separate queue manager for control messages
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
        self._execute_subscription = None
        self._execute_sub_key = None  # Add this to track subscription key
        self._start_time = datetime.now(timezone.utc)
    
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
        # Create separate queue managers for execute and control messages
        self.qm = QueueManager(client_name=self.worker_id, config=self.config.nats)
        self.control_qm = QueueManager(client_name=f"control_{self.worker_id}", config=self.config.nats)
        
        self.db = DatabaseManager()
        self.function_executor = FunctionExecutor(
            worker_id=self.worker_id,
            qm=self.qm,  # Use the main queue manager for function execution
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

            # Subscribe to control and execute messages
            await self._setup_control_subscription()
            await self._setup_execute_subscription()

            logger.info(f"Worker {self.worker_id} started and listening for messages...")
            self.set_status("idle")

        except Exception as e:
            logger.error(f"Failed to start worker: {e}")
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
                        try:
                            if self._execute_subscription:
                                # Delete the consumer from the stream using the unique durable name
                                await self._execute_subscription.unsubscribe()
                                # Clean up local subscription reference
                                self._execute_subscription = None
                                self.set_status("paused")
                                logger.info("Successfully unsubscribed from execute messages")
                        except Exception as e:
                            logger.warning(f"Error unsubscribing worker: {e}")
                        
                        # Send acknowledgment
                        await self.control_qm.publish_message(
                            subject="function.control.response",
                            stream="FUNCTION_CONTROL_RESPONSE",
                            message={
                                "processor_id": self.worker_id,
                                "type": "worker",
                                "status": "paused",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        self.set_status("paused")
                        logger.info("Successfully unsubscribed from execute messages")
                    
                    elif command == "unpause":
                        logger.info("Received unpause command")
                        self.state = ProcessorState.RUNNING
                        try:
                            if not self._execute_subscription:
                                await self._setup_execute_subscription()
                        except Exception as e:
                            logger.error(f"Error resubscribing worker: {e}")
                        
                        # Send acknowledgment
                        await self.control_qm.publish_message(
                            subject="function.control.response",
                            stream="FUNCTION_CONTROL_RESPONSE",
                            message={
                                "processor_id": self.worker_id,
                                "type": "worker",
                                "status": "running",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        self.set_status("idle")
                        logger.info("Successfully resubscribed to execute messages")
                    
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
                    elif command == "report":
                        logger.info("Received report command")
                        report = await self.generate_report()
                        logger.debug(f"Report: {report}")
                        # Send report through control response channel
                        await self.control_qm.publish_message(
                            subject="function.control.response",
                            stream="FUNCTION_CONTROL_RESPONSE",
                            message={
                                "processor_id": self.worker_id,
                                "type": "worker",
                                "command": "report",
                                "report": report,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        logger.debug("Worker report sent")
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
        logger.debug(f"Message handler called with message type: {type(msg)}")
        logger.debug(f"Message content: {msg}")
        
        if self.state == ProcessorState.PAUSED or not self._execute_subscription:
            logger.debug(f"Worker is paused (state: {self.state}) or no subscription (subscription: {self._execute_subscription}), skipping message")
            if hasattr(msg, 'ack'):
                await msg.ack()
            return

        self._last_message_time = datetime.now(timezone.utc)
        logger.debug("Processing message in message_handler")
        processing_lock_acquired = False
        
        try:
            # Try to acquire the processing lock
            async with self._processing_lock:
                if self._processing:
                    logger.info("Already processing a job, skipping new message")
                    if hasattr(msg, 'ack'):
                        await msg.ack()
                    return
                self._processing = True
                processing_lock_acquired = True
                logger.debug("Acquired processing lock")

            try:
                # Parse message
                logger.debug("Attempting to parse message")
                function_execution_request = FunctionExecutionRequest(
                    program_id=msg.get('program_id'),
                    function_name=msg.get('function'),
                    params=msg.get('params'),
                    force=msg.get("force", False)
                )
                logger.debug(f"Created function execution request: {function_execution_request}")
                
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
                self.set_status(f"busy:{function_execution_request.function_name}:{function_execution_request.params.get('target')}")
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
            self.set_status(f"idle")

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
        
        # Disconnect both queue managers
        if self.qm:
            await self.qm.disconnect()
        if self.control_qm:
            await self.control_qm.disconnect()
            
        logger.info("Worker shutdown complete")

    async def _health_check(self):
        """Monitor worker health and subscription status."""
        while True:
            try:
                if self.state == ProcessorState.PAUSED:
                    logger.info("Worker is paused. Skipping health check.")
                    await asyncio.sleep(30)
                    continue
                
                current_time = datetime.now(timezone.utc)
                
                # Check NATS connection
                if not self.qm.nc.is_connected:
                    logger.error("NATS connection lost. Attempting to reconnect...")
                    await self.qm.ensure_connected()
                
                # Check subscription status
                if not self._execute_subscription:
                    logger.warning("Execute subscription not found. Attempting to resubscribe...")
                    await self._reconnect_subscriptions()
                
                if self._last_message_time:
                    time_since_last_message = current_time - self._last_message_time
                    if time_since_last_message > timedelta(minutes=5):
                        logger.warning(f"No messages received for {time_since_last_message}. Checking connection...")
                        if self.qm.nc.is_connected:
                            logger.info("NATS connection is active")
                        else:
                            logger.error("NATS connection lost")
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                logger.exception(e)
                await asyncio.sleep(5)
    
    async def _reconnect_subscriptions(self):
        """Reconnect all subscriptions."""
        try:
            logger.info("Reconnecting subscriptions...")
            await self._setup_control_subscription()
            await self._setup_execute_subscription()
            logger.info("Successfully reconnected subscriptions")
        except Exception as e:
            logger.error(f"Error reconnecting subscriptions: {e}")

    async def _setup_execute_subscription(self):
        """Helper method to set up the function.execute subscription."""
        logger.debug("Setting up execute subscription...")
        self._execute_subscription = await self.qm.subscribe(
            subject="function.execute",
            stream="FUNCTION_EXECUTE",
            durable_name=None,  # Remove durable name
            message_handler=self.message_handler,
            batch_size=1,
            consumer_config={
                'ack_policy': AckPolicy.EXPLICIT,
                'deliver_policy': DeliverPolicy.NEW,
                'replay_policy': ReplayPolicy.INSTANT,
                'deliver_group': "workers",
                'max_deliver': 1
            },
            queue_group="workers",
            broadcast=False
        )
        self._execute_sub_key = f"FUNCTION_EXECUTE:function.execute:workers"
        logger.debug(f"Execute subscription created: {self._execute_subscription}")

    async def _setup_control_subscription(self):
        """Helper method to set up the function.control subscription."""
        logger.debug("Setting up control subscription...")
        await self.control_qm.subscribe(
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
        logger.debug("Successfully subscribed to control messages")

    async def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive report of the worker's current state."""
        try:
            # Get process info
            process = psutil.Process()
            cpu_percent = process.cpu_percent(interval=1)
            mem_info = process.memory_info()
            
            # Get current execution info
            current_execution = None
            if self._processing and self.running_tasks:
                task_id = next(iter(self.running_tasks))
                current_execution = {
                    "execution_id": task_id,
                    "module": self.function_executor.current_module if hasattr(self.function_executor, 'current_module') else None,
                    "target": self.function_executor.current_target if hasattr(self.function_executor, 'current_target') else None,
                    "start_time": self.function_executor.current_start_time.isoformat() if hasattr(self.function_executor, 'current_start_time') else None
                }
            
            # Get queue subscription info
            execute_sub_info = {
                "active": self._execute_subscription is not None,
                "subscription_key": self._execute_sub_key if self._execute_subscription else None,
                "queue_group": "workers"
            }
            
            # Get running tasks info
            tasks_info = []
            for exec_id, task in self.running_tasks.items():
                tasks_info.append({
                    "execution_id": exec_id,
                    "status": "running" if not task.done() else "completed",
                    "cancelled": task.cancelled()
                })

            report = {
                "worker": {
                    "id": self.worker_id,
                    "version": __version__,
                    "hostname": socket.gethostname(),
                    "state": self.state.value,
                    "uptime": (datetime.now(timezone.utc) - self._start_time).total_seconds() if hasattr(self, '_start_time') else None,
                    "last_message_time": self._last_message_time.isoformat() if self._last_message_time else None,
                    "current_execution": current_execution
                },
                "system": {
                    "platform": platform.platform(),
                    "python_version": sys.version,
                    "cpu_count": psutil.cpu_count(),
                    "total_memory": psutil.virtual_memory().total
                },
                "process": {
                    "cpu_percent": cpu_percent,
                    "memory_usage": {
                        "rss": mem_info.rss,  # Resident Set Size
                        "vms": mem_info.vms,  # Virtual Memory Size
                        "percent": process.memory_percent()
                    },
                    "threads": process.num_threads()
                },
                "queues": {
                    "nats_connected": self.qm.nc.is_connected if self.qm else False,
                    "execute_subscription": execute_sub_info,
                    "control_subscription": {
                        "active": True if self.control_qm else False,
                        "durable_name": f"CONTROL_{self.worker_id}"
                    }
                },
                "execution": {
                    "processing": self._processing,
                    "running_tasks": len(self.running_tasks),
                    "tasks": tasks_info
                },
                "redis": {
                    "status_connection": bool(self.redis_status.ping() if self.redis_status else False),
                    "cache_connection": bool(self.redis_cache.ping() if self.redis_cache else False)
                }
            }
            
            return report
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return {"error": str(e)}

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