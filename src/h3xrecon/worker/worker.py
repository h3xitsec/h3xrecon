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
import redis
import random
@dataclass
class FunctionExecutionRequest:
    function_name: str
    program_id: int
    params: Dict[str, Any]
    force: bool
    execution_id: Optional[str] = str(uuid.uuid4())
    timestamp: Optional[str] = datetime.now(timezone.utc).isoformat()

class Worker:
    def __init__(self, config: Config):
        self.worker_id = f"worker-{socket.gethostname()}-{random.randint(1000, 9999)}"
        self.config = config
        self.config.setup_logging()
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
        

    async def start(self):
        logger.info(f"Starting Worker (Worker ID: {self.worker_id}) version {__version__}...")
        try:
            # Run preflight checks
            preflight = PreflightCheck(self.config, f"worker-{self.worker_id}")
            if not await preflight.run_checks():
                raise ConnectionError("Preflight checks failed. Cannot start worker.")

            # Initialize components
            await self.initialize_components()
            
            # Connect to NATS and subscribe
            await self.qm.connect()
            # Subscribe to control messages
            await self.qm.subscribe(
                subject="function.control",
                stream="FUNCTION_CONTROL",
                durable_name=f"CONTROL_{self.worker_id}",
                message_handler=self.control_message_handler,
                batch_size=1,
                consumer_config={
                    'ack_policy': AckPolicy.NONE,  # No acks needed for control messages
                    'deliver_policy': DeliverPolicy.ALL,
                    'replay_policy': ReplayPolicy.INSTANT
                },
                broadcast=True
            )
            await self.qm.subscribe(
                subject="function.execute",
                stream="FUNCTION_EXECUTE",
                durable_name="MY_CONSUMER",
                message_handler=self.message_handler,
                batch_size=1
            )
            logger.info(f"Worker {self.worker_id} started and listening for messages...")
        except Exception as e:
            logger.error(f"Failed to start worker: {str(e)}")
            sys.exit(1)

    async def control_message_handler(self, msg):
        try:
            if isinstance(msg, dict):
                messages = [msg]
            else:
                messages = msg
            for message in messages:
                try:
                    logger.debug(f"Received control message: {message}")
                    command = message.get('command')
                    execution_id = message.get('execution_id')
                    target_worker_id = message.get('target_worker_id')
                    
                    if target_worker_id and target_worker_id != self.worker_id:
                        continue
                        
                    if command == 'killjob':
                        if len(list(self.running_tasks.keys())) > 0:
                            execution_id = list(self.running_tasks.keys())[0]
                            task = self.running_tasks.get(execution_id)
                            if task:
                                logger.debug(f"Killing job with Execution ID: {execution_id}")
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    logger.info(f"Successfully cancelled task {execution_id}")
                        else:
                            logger.warning(f"No running tasks found to kill")
                            
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

                    # Acknowledge the message
                    if hasattr(msg, 'ack'):
                        await msg.ack()

                except Exception as e:
                    logger.error(f"Error processing individual control message: {e}")
                    if hasattr(msg, 'ack'):
                        await msg.ack()
                    continue

        except Exception as e:
            logger.error(f"Error processing control message batch: {e}")
            logger.exception(e)
            if hasattr(msg, 'ack'):
                await msg.ack()
    
    async def should_execute(self, function_execution_request: FunctionExecutionRequest) -> bool:
        data = function_execution_request
        redis_key = f"{data.function_name}:{data.params.get('target')}"
        last_execution = self.redis_cache.get(redis_key)
        if last_execution:
            last_execution_time = datetime.fromisoformat(last_execution.decode())
            time_since_last_execution = datetime.now(timezone.utc) - last_execution_time
            skip = not time_since_last_execution > self.execution_threshold
            if skip:
                logger.info(f"Skipping {data.function_name} on {data.params.get('target')} : executed recently.")
            return not skip
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
        try:
            # Check if we're already processing a message
            async with self._processing_lock:
                if self._processing:
                    logger.info("Already processing a job, skipping new message")
                    return  # Skip this message, it will be redelivered
                
                self._processing = True

            try:
                if isinstance(msg, dict):
                    messages = [msg]
                else:
                    messages = msg

                for message in messages:
                    function_execution_request = FunctionExecutionRequest(
                        program_id=message.get('program_id'),
                        function_name=message.get('function'),
                        params=message.get('params'),
                        force=message.get("force", False)
                    )
                    
                    await self.validate_function_execution_request(function_execution_request)
                    if not function_execution_request.force:
                        if not await self.should_execute(function_execution_request):
                            continue

                    # Create and track the task
                    task = asyncio.create_task(
                        self.run_function_execution(function_execution_request)
                    )
                    self.running_tasks[function_execution_request.execution_id] = task

                    # Add callback to remove task when done
                    task.add_done_callback(
                        lambda t, eid=function_execution_request.execution_id: self.running_tasks.pop(eid, None)
                    )

                    try:
                        # Instead of awaiting the task directly, use asyncio.shield to prevent cancellation
                        # and wait_for to allow other tasks to run
                        await asyncio.wait(
                            [asyncio.shield(task)],
                            return_when=asyncio.ALL_COMPLETED
                        )
                    except asyncio.CancelledError:
                        # If the task was cancelled, we still want to wait for it to clean up
                        await task

            finally:
                async with self._processing_lock:
                    self._processing = False

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.exception(e)
    
    async def run_function_execution(self, request: FunctionExecutionRequest):
        try:
            logger.info(f"Running function {request.function_name} on {request.params.get('target')} ({request.execution_id})")
            async for result in self.function_executor.execute_function(
                    func_name=request.function_name,
                    params=request.params,
                    program_id=request.program_id,
                    execution_id=request.execution_id,
                    timestamp=request.timestamp,
                    force_execution=request.force
                ):
                pass  # Handle the result as needed
            
        except asyncio.CancelledError:
            logger.info(f"Execution {request.execution_id} was cancelled.")
        except Exception as e:
            logger.error(f"Error executing function {request.execution_id}: {e}")
            raise

    async def stop(self):
        logger.info("Shutting down...")
        # Cancel all running tasks
        for execution_id, task in self.running_tasks.items():
            task.cancel()
            logger.info(f"Cancelled task with Execution ID: {execution_id}")
        await self.qm.disconnect()

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