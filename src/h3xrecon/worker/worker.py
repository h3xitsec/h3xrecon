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
from enum import Enum
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

class Worker(ReconComponent):
    def __init__(self, config: Config):
        super().__init__("worker", config)
        self.function_executor = None
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self._execution_semaphore = asyncio.Semaphore(1)
        self._processing = False
        self._processing_lock = asyncio.Lock()

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
                    durable_name=f"WORKERS_EXECUTE_{self.component_id}",
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
                self._sub_key = f"FUNCTION_EXECUTE:function.execute:WORKERS_EXECUTE_{self.component_id}"
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
            
            # Validation
            function_valid = await self.validate_function_execution_request(function_execution_request)
            if not function_valid:
                logger.info(f"Skipping execution: {function_execution_request.function_name}")
                await raw_msg.ack()
                return

            await self.set_status(f"busy:{function_execution_request.function_name}:{function_execution_request.params.get('target')}")
            # Execution
            task = asyncio.create_task(
                self.run_function_execution(function_execution_request)
            )
            self.running_tasks[function_execution_request.execution_id] = task
            await task
                
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            logger.exception(e)
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
                    raise asyncio.CancelledError()
                
                result_count += 1
                logger.debug(f"Execution {msg_data.execution_id}: Result #{result_count}: {result}")
                
        except asyncio.CancelledError:
            logger.info(f"Execution {msg_data.execution_id} was cancelled.")
            raise
        except Exception as e:
            logger.error(f"Error executing function {msg_data.execution_id}: {e}")
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
