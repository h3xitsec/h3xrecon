import asyncio
import socket
import sys
from loguru import logger
from h3xrecon.worker.executor import FunctionExecutor
from h3xrecon.core import QueueManager, DatabaseManager, Config, PreflightCheck
from h3xrecon.core.utils import debug_trace
from h3xrecon.__about__ import __version__
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from nats.js.errors import NotFoundError
from dataclasses import dataclass
from typing import Dict, Any, Optional
import uuid
from datetime import datetime, timezone, timedelta
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
        self.role = "worker"
        self.component_id = f"{self.role}-{socket.gethostname()}-{random.randint(1000, 9999)}"
        self.worker_id = self.component_id
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
        self._pull_processor_task = None  # Add task tracking for pull processor
        self._subscription_lock = asyncio.Lock()  # Add lock for subscription operations
        self._start_time = datetime.now(timezone.utc)
        self.running = asyncio.Event()
        self.running.set()  # Start in running state

    @debug_trace
    async def set_status(self, status: str):
        self.redis_status.set(self.component_id, status)
        for attempt in range(5):
            current_status = self.redis_status.get(self.component_id).decode()
            logger.debug(f"Current status: {current_status}, Target status: {status}")
            if current_status != status:
                logger.error(f"Failed to set status for {self.component_id} to {status} (attempt {attempt + 1}/5)")
                if attempt < 4:  # Don't sleep on last attempt
                    await asyncio.sleep(1)
            else:
                logger.debug(f"Successfully set status for {self.component_id} to {status}")
                break

    @debug_trace
    async def start(self):
        logger.info(f"Starting Worker (Worker ID: {self.worker_id}) version {__version__}...")
        try:
            # Initialize components
            await self.initialize_components()
            await self.qm.ensure_connected()
            await self.control_qm.ensure_connected()
            # Run preflight checks
            preflight = PreflightCheck(self.config, f"worker-{self.worker_id}")
            if not await preflight.run_checks():
                logger.error("Preflight checks failed. Exiting.")
                sys.exit(1)
            
            # Setup subscriptions
            await self._setup_control_subscription()
            await self._setup_execute_subscription()
            # Start health check
            #self._health_check_task = asyncio.create_task(self._health_check())
            # Subscribe to control and execute messages

            logger.info(f"Worker {self.worker_id} started and listening for messages...")
            await self.set_status("idle")

        except Exception as e:
            logger.error(f"Failed to start worker: {e}")
            logger.exception(e)
            sys.exit(1)

    @debug_trace
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
            qm=self.qm,
            db=self.db,
            config=self.config,
            redis_status=self.redis_status
        )


    @debug_trace
    async def _setup_control_subscription(self):
        """Helper method to set up the function.control subscription."""
        logger.debug("Setting up control subscription...")
        
        # Subscribe to broadcast messages (all components)
        await self.control_qm.subscribe(
            subject="function.control.all",
            stream="FUNCTION_CONTROL",
            durable_name=f"CONTROL_ALL_{self.worker_id}",
            message_handler=self.control_message_handler,
            batch_size=1,
            consumer_config={
                'ack_policy': AckPolicy.EXPLICIT,
                'deliver_policy': DeliverPolicy.NEW,
                'replay_policy': ReplayPolicy.INSTANT
            },
            broadcast=True
        )

        # Subscribe to broadcast messages (all workers)
        await self.control_qm.subscribe(
            subject="function.control.all_worker",
            stream="FUNCTION_CONTROL",
            durable_name=f"CONTROL_ALL_WORKER_{self.worker_id}",
            message_handler=self.control_message_handler,
            batch_size=1,
            consumer_config={
                'ack_policy': AckPolicy.EXPLICIT,
                'deliver_policy': DeliverPolicy.NEW,
                'replay_policy': ReplayPolicy.INSTANT
            },
            broadcast=True
        )
        
        # Subscribe to worker-specific messages
        await self.control_qm.subscribe(
            subject=f"function.control.{self.worker_id}",
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
        
        logger.info("Successfully subscribed to control channels")

    @debug_trace
    async def _setup_execute_subscription(self):
        """Helper method to set up the function.execute subscription."""
        logger.debug("Setting up execute subscription...")
        try:
            async with self._subscription_lock:  # Use lock to prevent concurrent setup
                if self.state == ProcessorState.PAUSED:
                    logger.debug("Worker is paused, skipping execute subscription setup")
                    return

                # Clean up existing subscription and task
                if self._execute_subscription:
                    try:
                        await self._execute_subscription.unsubscribe()
                        logger.debug("Successfully unsubscribed from execute subscription")
                    except NotFoundError:
                        logger.debug("Execute subscription already deleted.")
                    except Exception as e:
                        logger.warning(f"Error unsubscribing from execute subscription: {e}")
                    finally:
                        self._execute_subscription = None

                # Cancel existing pull processor task
                if self._pull_processor_task and not self._pull_processor_task.done():
                    self._pull_processor_task.cancel()
                    try:
                        await self._pull_processor_task
                    except asyncio.CancelledError:
                        pass
                    self._pull_processor_task = None

                subscription = await self.qm.subscribe(
                    subject="function.execute",
                    stream="FUNCTION_EXECUTE",
                    durable_name=f"WORKERS_EXECUTE",
                    message_handler=self.message_handler,
                    batch_size=1,
                    queue_group="workers",
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.ALL,
                        'replay_policy': ReplayPolicy.INSTANT,
                        'max_deliver': 1,
                        'max_ack_pending': 1000,
                        'flow_control': False,  # Disable flow control for pull-based
                        #'deliver_group': 'workers'  # Ensure queue group is set in config
                    },
                    pull_based=True  # Enable pull-based subscription
                )
                self._execute_subscription = subscription
                self._execute_sub_key = f"FUNCTION_EXECUTE:function.execute:WORKERS_EXECUTE"
                logger.info("Successfully subscribed to execute channel")
                
                # Start the pull message processing loop with proper task tracking
                await self.start_pull_processor()

        except Exception as e:
            logger.error(f"Error setting up execute subscription: {e}")
            raise
    
    @debug_trace
    async def start_pull_processor(self):
        if not self._pull_processor_task or self._pull_processor_task.done():
            self._pull_processor_task = asyncio.create_task(self._process_pull_messages())
    
    @debug_trace
    async def _process_pull_messages(self):
        """Process messages from the pull-based subscription."""
        logger.debug(f"{self.worker_id}: Starting pull message processing loop")
        while True:
            try:
                if self.state == ProcessorState.PAUSED:
                    await asyncio.sleep(1)
                    continue

                if not self._execute_subscription:
                    logger.debug("No execute subscription found")
                    await self._setup_execute_subscription()
                    continue

                # Fetch one message
                messages = await self.qm.fetch_messages(self._execute_subscription, batch_size=1)
                if not messages:
                    await asyncio.sleep(0.1)
                    continue

                message = messages[0]
                # Process the message
                await self.message_handler(message)

            except asyncio.CancelledError:
                logger.info("Pull message processing loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in pull message processing loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    # @debug_trace
    # async def _process_pull_messages(self):
    #     """Process messages from the pull-based subscription."""
    #     while True:
    #         logger.debug(f"{self.worker_id} state: {self.state}")
    #         if self.state == ProcessorState.PAUSED or self.state == ProcessorState.BUSY:
    #             await asyncio.sleep(1)
    #             continue

    #         try:
    #             # Check if we're already processing
    #             async with self._processing_lock:
    #                 if self._processing:
    #                     logger.debug("Already processing a message, waiting...")
    #                     await asyncio.sleep(1)
    #                     continue

    #             # Check if we have a valid subscription
    #             if not self._execute_subscription:
    #                 logger.debug("No execute subscription found")
    #                 await self._setup_execute_subscription()
    #                 continue

    #             # Fetch messages
    #             #logger.debug("Attempting to fetch messages...")
    #             messages = await self.qm.fetch_messages(self._execute_subscription, batch_size=1)
                
    #             if messages:
    #                 logger.debug(f"Received {len(messages)} messages")
    #                 for msg in messages:
    #                     # Process each message
    #                     await self.message_handler(msg)
    #             else:
    #                 #logger.debug("No messages received, waiting...")
    #                 await asyncio.sleep(0.1)

    #         except asyncio.CancelledError:
    #             logger.info("Pull message processing loop cancelled")
    #             break
    #         except Exception as e:
    #             if not isinstance(e, TimeoutError):
    #                 logger.error(f"Error in pull message processing loop: {e}")
    #             await asyncio.sleep(0.1)
    @debug_trace
    async def unsubscribe_execute_subscription(self):
        logger.debug("Unsubscribing from execute subscription")
        if self._execute_subscription:
            await self._execute_subscription.unsubscribe()
            self._execute_subscription = None

    @debug_trace
    async def message_handler(self, raw_msg):
        logger.debug(f"Worker {self.worker_id} received message: {raw_msg.data}")
        """Handle incoming messages with proper synchronization."""
        if self.state == ProcessorState.PAUSED:
            await raw_msg.nak()
            return
        try:
            self.state = ProcessorState.BUSY
            msg = json.loads(raw_msg.data.decode())
            self._last_message_time = datetime.now(timezone.utc)
            logger.debug(f"Processing message: {msg}")

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
        # try:
        #     # Use processing lock for the entire message handling to prevent race conditions
        #     async with self._processing_lock:
        #         if self._processing:
        #             logger.warning("Already processing a message, rejecting new message")
        #             # First unsubscribe to prevent more messages
        #             #await self.unsubscribe_execute_subscription()
        #             # Then NAK the message so it can be processed by other workers
        #             await raw_msg.nak()
        #             logger.debug(f"{self.worker_id} nak'd message: {raw_msg.data}")
        #             return

        #         # Set state to busy and unsubscribe atomically
        #         self._processing = True
        #         self.state = ProcessorState.BUSY
        #         await self.set_status(f"busy")
        #         #await self.unsubscribe_execute_subscription()

        #         try:
        #             msg = json.loads(raw_msg.data.decode())
        #             self._last_message_time = datetime.now(timezone.utc)
        #             logger.debug(f"Processing message: {msg}")

        #             # Parse message
        #             logger.debug("Attempting to parse message")
        #             function_execution_request = FunctionExecutionRequest(
        #                 program_id=msg.get('program_id'),
        #                 function_name=msg.get('function'),
        #                 params=msg.get('params'),
        #                 force=msg.get("force", False)
        #             )
        #             logger.debug(f"Created function execution request: {function_execution_request}")
                    
        #             # Validation
        #             function_valid = await self.validate_function_execution_request(function_execution_request)
        #             logger.debug(f"Function valid: {function_valid}")
        #             await self.set_status(f"busy:{function_execution_request.function_name}:{function_execution_request.params.get('target')}")
        #             if not function_valid:
        #                 logger.info(f"Skipping execution: {function_execution_request.function_name}")
        #                 await raw_msg.ack()  # ACK invalid messages to prevent redelivery
        #                 return
                            
        #             if not function_execution_request.force:
        #                 if not await self.should_execute(function_execution_request):
        #                     logger.info(f"Skipping execution: {function_execution_request.function_name}")
        #                     await raw_msg.ack()
        #                     logger.debug(f"{self.worker_id} acknowledged message: {raw_msg.data}")
        #                     return
                        
        #             # Create and store the task
        #             task = asyncio.create_task(
        #                 self.run_function_execution(function_execution_request)
        #             )
        #             self.running_tasks[function_execution_request.execution_id] = task
                    
        #             try:
        #                 logger.debug(f"Waiting for task {function_execution_request.execution_id} to complete")
        #                 await task
        #                 logger.debug(f"Task {function_execution_request.execution_id} completed successfully")
        #             except asyncio.CancelledError:
        #                 logger.warning(f"Task {function_execution_request.execution_id} was cancelled")
        #                 # Don't clean up here, let the killjob handler do it
        #                 raise
        #             except Exception as e:
        #                 logger.error(f"Error in task execution: {e}")
        #                 logger.exception(e)
        #                 # Clean up on non-cancellation errors
        #                 self.running_tasks.pop(function_execution_request.execution_id, None)
        #                 raise
        #             else:
        #                 # Clean up only on successful completion
        #                 self.running_tasks.pop(function_execution_request.execution_id, None)
                    
        #         except asyncio.CancelledError:
        #             # Let cancellation propagate up
        #             raise
        #         except Exception as e:
        #             logger.error(f"Error processing message: {e}")
        #             logger.exception(e)
        #         finally:
        #             # Acknowledge the message after processing, unless it's already acknowledged
        #             if not raw_msg._ackd:
        #                 await raw_msg.ack()
        #                 logger.debug(f"{self.worker_id} acknowledged message: {raw_msg.data}")
        #             if self.state != ProcessorState.PAUSED:
        #                 self.state = ProcessorState.RUNNING
        #                 await self.set_status("idle")
        #             # # Always try to resubscribe and reset state, even if there was an error
        #             # try:
        #             #     if self.state != ProcessorState.PAUSED:
        #             #         self.state = ProcessorState.RUNNING
        #             #         await self.set_status("idle")
        #             #         await self._setup_execute_subscription()
        #             # except Exception as e:
        #             #     logger.error(f"Error resubscribing: {e}")
        #             #     # If we can't resubscribe, we need to make sure we're in a known state
        #             #     self.state = ProcessorState.PAUSED
        #             #     await self.set_status("error")
        #             # finally:
        #             #     self._processing = False
                
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            logger.exception(e)
        finally:
            if not raw_msg._ackd:
                await raw_msg.ack()
            await self.set_status("idle")

    @debug_trace
    async def control_message_handler(self, raw_msg):
        """Handle control messages for pausing/unpausing the processor"""
        try:
            msg = json.loads(raw_msg.data.decode())
            command = msg.get("command")
            target = msg.get("target", "all")
            target_id = msg.get("target_id")
            
            # Check if message is targeted for this worker
            if target not in ["all", "worker"] and target != self.worker_id:
                logger.debug(f"Ignoring control message - not for this worker (target: {target})")
                await raw_msg.ack()
                return
            
            # For worker-specific targeting, check if this is the intended worker
            if target == "worker" and target_id and target_id != self.worker_id:
                logger.debug(f"Ignoring worker-specific message - not for this worker ID (target_id: {target_id})")
                await raw_msg.ack()
                return

            if command == "pause":
                logger.debug(f"Received pause command for {target} {target_id or ''}")
                if self.state == ProcessorState.PAUSED:
                    logger.debug("Worker is already paused, sending response")
                    # Send acknowledgment even when already paused
                    await self.control_qm.publish_message(
                        subject="control.response.pause",
                        stream="CONTROL_RESPONSE_PAUSE",
                        message={
                            "component_id": self.worker_id,
                            "type": "worker",
                            "status": "paused",
                            "success": True,
                            "command": "pause",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    await raw_msg.ack()
                    return
                    
                self.state = ProcessorState.PAUSED
                # Unsubscribe from execute subscriptions
                # if self._execute_subscription:
                #     try:
                #         await self._execute_subscription.unsubscribe()
                #         logger.debug(f"Unsubscribed from execute subscription: {self._execute_subscription}")
                #     except Exception as e:
                #         logger.warning(f"Error unsubscribing from execute subscription: {e}")
                #     finally:
                #         self._execute_subscription = None
                        
                await self.set_status("paused")
                logger.info(f"Worker {self.worker_id} paused")
                
                # Send acknowledgment to dedicated stream
                await self.control_qm.publish_message(
                    subject="control.response.pause",
                    stream="CONTROL_RESPONSE_PAUSE",
                    message={
                        "component_id": self.worker_id,
                        "type": "worker",
                        "status": "paused",
                        "success": True,
                        "command": "pause",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            
            elif command == "unpause":
                logger.debug("Received unpause command")
                try:
                    # Reset processing state first
                    async with self._processing_lock:
                        self._processing = False
                        self.state = ProcessorState.RUNNING

                    # # Ensure we don't have an existing subscription
                    # if self._execute_subscription:
                    #     try:
                    #         await self._execute_subscription.unsubscribe()
                    #     except Exception as e:
                    #         logger.warning(f"Error unsubscribing existing subscription: {e}")
                    #     finally:
                    #         self._execute_subscription = None

                    # Resubscribe to the execute stream with a small delay
                    await asyncio.sleep(0.5)  # Add a small delay before resubscribing
                    #await self._setup_execute_subscription()
                    
                    # Verify subscription was successful
                    #if not self._execute_subscription:
                    #    raise Exception("Failed to reestablish execute subscription")

                    #logger.debug(f"Resubscribed to execute subscription: {self._execute_subscription}")
                    await self.set_status("idle")
                    logger.info(f"Worker {self.worker_id} resumed")
                    
                    # Send acknowledgment to dedicated stream
                    await self.control_qm.publish_message(
                        subject="control.response.unpause",
                        stream="CONTROL_RESPONSE_UNPAUSE",
                        message={
                            "component_id": self.worker_id,
                            "type": "worker",
                            "status": "running",
                            "success": True,
                            "command": "unpause",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                except Exception as e:
                    logger.error(f"Error during unpause: {e}")
                    self.state = ProcessorState.PAUSED
                    await self.set_status("paused")
                    # Send error response
                    await self.control_qm.publish_message(
                        subject="control.response.unpause",
                        stream="CONTROL_RESPONSE_UNPAUSE",
                        message={
                            "component_id": self.worker_id,
                            "type": "worker",
                            "status": "paused",
                            "success": False,
                            "error": str(e),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
            
            elif command == 'killjob':
                logger.info("Received kill job command")
                success = False
                error_msg = None
                
                try:
                    if self.running_tasks:
                        # Cancel all running tasks
                        for execution_id, task in list(self.running_tasks.items()):
                            logger.debug(f"Killing job with Execution ID: {execution_id}")
                            if not task.done():
                                task.cancel()
                                try:
                                    # Wait for task to actually cancel with a timeout
                                    await asyncio.wait_for(task, timeout=5.0)
                                except asyncio.TimeoutError:
                                    logger.warning(f"Task {execution_id} taking too long to cancel")
                                except asyncio.CancelledError:
                                    logger.info(f"Successfully cancelled task {execution_id}")
                                    success = True
                                except Exception as e:
                                    error_msg = str(e)
                                    logger.error(f"Error cancelling task: {error_msg}")
                                finally:
                                    # Clean up the cancelled task
                                    self.running_tasks.pop(execution_id, None)
                                    await self.set_status("idle")
                        
                        # Reset worker state and processing lock
                        # async with self._processing_lock:
                        #     self._processing = False
                        #     if self.state != ProcessorState.PAUSED:
                        #         self.state = ProcessorState.RUNNING
                        
                            
                        # Clean up execute subscription
                        #if self._execute_subscription:
                        #    try:
                        #        await self._execute_subscription.unsubscribe()
                        #        logger.debug("Successfully unsubscribed execute subscription")
                        #    except Exception as e:
                        #        logger.warning(f"Error unsubscribing execute subscription: {e}")
                        #    finally:
                        #        self._execute_subscription = None
                        
                        # Ensure execute subscription is active
                        await asyncio.sleep(0.5)  # Small delay before resubscribing
                        await self.start_pull_processor()
                        #await self._setup_execute_subscription()
                        #logger.debug("Re-established execute subscription after job kill")
                    else:
                        success = True  # No tasks running is still a success
                        logger.info("No running tasks to kill")
                    
                    # Send acknowledgment with success status
                    await self.control_qm.publish_message(
                        subject="control.response.killjob",
                        stream="CONTROL_RESPONSE_KILLJOB",
                        message={
                            "component_id": self.worker_id,
                            "command": "killjob",
                            "success": success,
                            "error": error_msg,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    logger.debug(f"Kill job response sent: {success}")
                    
                except Exception as e:
                    logger.error(f"Error processing kill command: {e}")
                    # Send error response
                    await self.control_qm.publish_message(
                        subject="control.response.killjob",
                        stream="CONTROL_RESPONSE_KILLJOB",
                        message={
                            "component_id": self.worker_id,
                            "command": "killjob",
                            "success": False,
                            "error": str(e),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                finally:
                    # Acknowledge the control message
                    await raw_msg.ack()
            
            elif command == "report":
                logger.info("Received report command")
                report = await self.generate_report()
                logger.debug(f"Report: {report}")
                # Send report through control response channel
                await self.control_qm.publish_message(
                    subject="function.control.response",
                    stream="FUNCTION_CONTROL_RESPONSE",
                    message={
                        "component_id": self.worker_id,
                        "type": "worker",
                        "command": "report",
                        "report": report,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                logger.debug("Worker report sent")
            elif command == 'ping':
                logger.info(f"Received ping from {msg.get('target')}")
                # Send pong response
                await self.control_qm.publish_message(
                    subject="control.response.ping",
                    stream="CONTROL_RESPONSE_PING",
                    message={
                        "component_id": self.worker_id,
                        "type": "worker",
                        "command": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            else:
                logger.warning(f"Received unknown control command or missing execution_id: {msg}")

            # Acknowledge the message after successful processing
            if not raw_msg._ackd:
                await raw_msg.ack()

        except Exception as processing_error:
            logger.error(f"Error processing individual control message: {processing_error}")
            logger.exception(processing_error)
            # Decide whether to acknowledge based on error type
            if not raw_msg._ackd:
                await raw_msg.ack()
            return

    @debug_trace
    async def should_execute(self, request: FunctionExecutionRequest) -> bool:
        """
        Determine whether a function should be executed based on the last execution time.
        """
        data = request
        # Extract relevant parameters for the Redis key
        target = data.params.get('target', '')
        
        logger.debug(f"Original params: {data.params}")
        
        # Handle extra_params specially if it exists as a list
        if 'extra_params' in data.params and isinstance(data.params['extra_params'], list):
            extra_params_str = f"extra_params={sorted(data.params['extra_params'])}"
            logger.debug(f"Using list extra_params: {extra_params_str}")
        else:
            # Create a sorted, filtered copy of params excluding certain keys
            extra_params = {k: v for k, v in sorted(data.params.items()) 
                           if k not in ['target', 'force'] and not k.startswith('--')}
            # Convert extra_params to a string representation
            extra_params_str = ':'.join(f"{k}={v}" for k, v in extra_params.items()) if extra_params else ''
            logger.debug(f"Using dict extra_params: {extra_params_str}")
        
        # Construct Redis key with extra parameters
        redis_key = f"{data.function_name}:{target}"
        if extra_params_str:
            redis_key = f"{redis_key}:{extra_params_str}"
        
        logger.debug(f"Using Redis key: {redis_key}")
        last_execution_bytes = self.redis_cache.get(redis_key)
        logger.debug(f"Raw last execution from Redis for key '{redis_key}': {last_execution_bytes}")

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

    @debug_trace
    async def validate_function_execution_request(self, function_execution_request: FunctionExecutionRequest) -> bool:
        # Validate function_name is a valid plugin
        try:
            # Dynamically import plugins to check if the function_name is valid
            plugin_found = False
            
            # Check if the function name exists in the function map keys
            plugin_found = any(function_execution_request.function_name in key for key in self.function_executor.function_map.keys())
            if not plugin_found:
                raise ValueError(f"Invalid function_name: {function_execution_request.function_name}. No matching plugin found.")
        
        except Exception as e:
            raise ValueError(f"Error validating function_name: {str(e)}")
        # TODO: Fix this to bring back program_name validation
        # Validate program_name exists in the database
        #try:
        #    program_name = await self.db.get_program_name(function_execution_request.program_id)
        #    if not program_name:
        #        raise ValueError(f"Invalid program_id: {function_execution_request.program_id}. Program not found in database.")
        #except Exception as e:
        #    raise ValueError(f"Error validating program_name: {str(e)}")
        return plugin_found

    @debug_trace
    async def run_function_execution(self, msg_data: FunctionExecutionRequest):
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
                    logger.info(f"Execution {msg_data.execution_id} was cancelled, stopping execution")
                    raise asyncio.CancelledError()
                
                result_count += 1
                logger.debug(f"Execution {msg_data.execution_id}: Received result #{result_count}: {result}")
                if not result:
                    logger.warning(f"Received empty result from {msg_data.function_name}")
                    continue
                
        except asyncio.CancelledError:
            logger.info(f"Execution {msg_data.execution_id} was cancelled.")
            raise
        except Exception as e:
            logger.error(f"Error executing function {msg_data.execution_id}: {e}")
            logger.exception(e)
            raise
        finally:
            logger.info(f"Finished execution of function '{msg_data.function_name}' with Execution ID: {msg_data.execution_id}. Total results: {result_count}")
            await self.set_status("idle")

    @debug_trace
    async def stop(self):
        logger.info("Shutting down...")
        # Cancel all running tasks
        for execution_id, task in list(self.running_tasks.items()):
            task.cancel()
            logger.info(f"Cancelled task with Execution ID: {execution_id}")
        
        # Clean up execute subscription
        if self._execute_subscription:
            try:
                await self._execute_subscription.unsubscribe()
                logger.debug("Successfully unsubscribed from execute subscription during shutdown")
            except Exception as e:
                logger.warning(f"Error unsubscribing from execute subscription during shutdown: {e}")
            self._execute_subscription = None
        
        # Disconnect both queue managers
        if self.qm:
            await self.qm.disconnect()
        if self.control_qm:
            await self.control_qm.disconnect()
            
        logger.info("Worker shutdown complete")

    @debug_trace
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
                if self.qm and not self.qm.nc.is_connected:
                    logger.error("NATS connection lost. Attempting to reconnect...")
                    await self.qm.ensure_connected()
                
                # Check subscription status
                if not self._execute_subscription:
                    logger.warning("Execute subscription not found. Attempting to resubscribe...")
                    await self._setup_execute_subscription()
                
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

    @debug_trace
    async def _reconnect_subscriptions(self):
        """Reconnect all subscriptions."""
        try:
            logger.info("Reconnecting subscriptions...")
            await self._setup_control_subscription()
            await self._setup_execute_subscription()
            logger.info("Successfully reconnected subscriptions")
        except Exception as e:
            logger.error(f"Error reconnecting subscriptions: {e}")

    @debug_trace
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
