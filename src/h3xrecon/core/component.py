import asyncio
import socket
import random
import redis
import psutil
import platform
import sys
import json
from datetime import datetime, timezone, timedelta
from h3xrecon.core.config import Config
from h3xrecon.core.utils import debug_trace
from enum import Enum
from loguru import logger
from typing import Dict, Any
from h3xrecon.core import QueueManager, DatabaseManager, PreflightCheck
from h3xrecon.__about__ import __version__

class ProcessorState(Enum):
    RUNNING = "idle"
    PAUSED = "paused"
    BUSY = "busy"

class ReconComponent:
    def __init__(self, role: str, config: Config):
        self.role = role
        self.component_id = f"{self.role}-{socket.gethostname()}-{random.randint(1000, 9999)}"
        self.config = config
        self.config.setup_logging()
        self.state = ProcessorState.RUNNING
        self.qm = QueueManager(client_name=self.component_id, config=config.nats)
        self.db = DatabaseManager()
        self.redis_status = None
        self.redis_cache = None
        self._health_check_task = None
        self._last_message_time = datetime.now(timezone.utc)
        self._subscription = None
        self._sub_key = None
        self._pull_processor_task = None
        self._subscription_lock = asyncio.Lock()
        self._start_time = datetime.now(timezone.utc)
        self._execution_semaphore = asyncio.Semaphore(1)
        self._processing = False
        self._processing_lock = asyncio.Lock()
        self.running = asyncio.Event()
        self.running.set()  # Start in running state

    async def initialize_redis(self):
        """Initialize Redis connections."""
        try:
            logger.debug(f"Connecting to Redis status db at {self.config.redis.host}:{self.config.redis.port} db=1")
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
            # Test connection
            self.redis_status.ping()
            logger.debug("Successfully connected to Redis status db")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def set_status(self, status: str):
        """Set component status in Redis."""
        if not self.redis_status:
            return
        try:
            old_status = self.redis_status.get(self.component_id).decode()
        except Exception as e:
            old_status = None
        if old_status == status:
            return
        self.redis_status.set(self.component_id, status)
        for attempt in range(5):
            current_status = self.redis_status.get(self.component_id).decode()
            logger.debug(f"Current status: {current_status}, Target status: {status}")
            if current_status != status:
                logger.error(f"Failed to set status for {self.component_id} to {status} (attempt {attempt + 1}/5)")
                if attempt < 4:  # Don't sleep on last attempt
                    await asyncio.sleep(1)
            else:
                logger.success(f"STATUS CHANGE: {old_status} -> {status}")
                break

    async def start_pull_processor(self):
        """Start the pull message processor task."""
        if self._pull_processor_task and not self._pull_processor_task.done():
            self._pull_processor_task.cancel()
            try:
                await self._pull_processor_task
            except asyncio.CancelledError:
                pass
        self._pull_processor_task = asyncio.create_task(self._process_pull_messages())
        logger.debug(f"{self.component_id}: Started new pull processor task")
    
    async def stop_pull_processor(self):
        """Stop the pull message processor task."""
        if self._pull_processor_task and not self._pull_processor_task.done():
            self._pull_processor_task.cancel()
            try:
                await self._pull_processor_task
            except asyncio.CancelledError:
                pass

    async def start(self):
        """Start the component with common initialization logic."""
        logger.info(f"STARTING {self.role.upper()} {self.component_id} : (v{__version__})")
        try:
            # Run preflight checks
            preflight = PreflightCheck(self.config, f"{self.role}-{self.component_id}")
            if not await preflight.run_checks():
                raise ConnectionError("Preflight checks failed")

            # Initialize Redis
            await self.initialize_redis()

            # Initialize components with retry logic
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                try:
                    await self.qm.connect()
                    await self.setup_subscriptions()
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        raise e
                    await asyncio.sleep(1)
            self._health_check_task = asyncio.create_task(self._health_check())
            if self.role == "jobprocessor":
                self._load_plugins()
            await self.start_pull_processor()
            await self.set_status("idle")
            logger.success(f"STARTED {self.role.upper()}: {self.component_id}")

        except Exception as e:
            logger.error(f"Failed to start {self.role}: {str(e)}")
            sys.exit(1)

    async def stop(self):
        """Stop the component and clean up resources."""
        logger.info(f"SHUTTING DOWN {self.role.upper()}: {self.component_id}")
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._pull_processor_task:
            self._pull_processor_task.cancel()
        if self._subscription:
            try:
                await self._subscription.unsubscribe()
            except Exception as e:
                logger.warning(f"Error unsubscribing: {e}")
        await self.qm.disconnect()
        if self.redis_status:
            self.redis_status.delete(self.component_id)
        logger.success(f"{self.role.upper()} SHUTDOWN COMPLETE")

    async def _cleanup_subscriptions(self):
        """Clean up existing subscriptions and consumers."""
        try:
            await self.stop_pull_processor()
            # Clean up existing subscriptions
            if self._subscription:
                try:
                    await self._subscription.unsubscribe()
                except Exception as e:
                    logger.warning(f"Error unsubscribing: {e}")
                self._subscription = None

            # Delete existing consumers if they exist
            if hasattr(self, 'qm') and self.qm and self.qm.js:
                try:
                    # Clean up consumers in FUNCTION_EXECUTE stream
                    try:
                        consumers = await self.qm.js.consumers_info("FUNCTION_EXECUTE")
                        for consumer in consumers:
                            if consumer.config.durable_name and consumer.config.durable_name.endswith(self.component_id):
                                try:
                                    await self.qm.js.delete_consumer("FUNCTION_EXECUTE", consumer.config.durable_name)
                                    logger.debug(f"Deleted consumer from FUNCTION_EXECUTE: {consumer.config.durable_name}")
                                except Exception as e:
                                    logger.warning(f"Error deleting consumer {consumer.config.durable_name}: {e}")
                    except Exception as e:
                        logger.warning(f"Error cleaning up FUNCTION_EXECUTE consumers: {e}")

                    # Clean up consumers in FUNCTION_CONTROL stream
                    try:
                        consumers = await self.qm.js.consumers_info("FUNCTION_CONTROL")
                        for consumer in consumers:
                            if consumer.config.durable_name and consumer.config.durable_name.endswith(self.component_id):
                                try:
                                    await self.qm.js.delete_consumer("FUNCTION_CONTROL", consumer.config.durable_name)
                                    logger.debug(f"Deleted consumer from FUNCTION_CONTROL: {consumer.config.durable_name}")
                                except Exception as e:
                                    logger.warning(f"Error deleting consumer {consumer.config.durable_name}: {e}")
                    except Exception as e:
                        logger.warning(f"Error cleaning up FUNCTION_CONTROL consumers: {e}")

                    # Add a small delay to ensure cleanup is complete
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.warning(f"Error cleaning up consumers: {e}")
        except Exception as e:
            logger.error(f"Error in cleanup_subscriptions: {e}")

    async def setup_subscriptions(self):
        """Setup NATS subscriptions. Should be implemented by child classes."""
        raise NotImplementedError("Subclasses must implement setup_subscriptions")

    async def message_handler(self, raw_msg):
        """Handle incoming messages. Should be implemented by child classes."""
        raise NotImplementedError("Subclasses must implement message_handler")

    async def _process_pull_messages(self):
        """Process messages from the pull-based subscription."""
        logger.debug(f"{self.component_id}: Starting pull message processing loop")
        while True:
            if self.state == ProcessorState.PAUSED:
                await asyncio.sleep(1)
                continue

            try:
                # Check if we're already processing
                async with self._processing_lock:
                    if self._processing:
                        logger.debug(f"{self.component_id}: Already processing, sleeping...")
                        await asyncio.sleep(0.1)
                        continue
                    self._processing = True

                # Fetch one message
                try:
                    messages = await self.qm.fetch_messages(self._subscription, batch_size=1)
                    if not messages:
                        async with self._processing_lock:
                            self._processing = False
                        await asyncio.sleep(0.1)
                        continue

                    message = messages[0]
                    # Process the message
                    await self.message_handler(message)
                finally:
                    # Always ensure we reset the processing flag
                    async with self._processing_lock:
                        self._processing = False

            except asyncio.CancelledError:
                logger.debug("Pull message processing loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in pull message processing loop: {e}", exc_info=True)
                await asyncio.sleep(1)
                # Ensure processing flag is reset on error
                async with self._processing_lock:
                    self._processing = False
                logger.debug(f"{self.component_id}: Released processing lock after error")

    async def _health_check(self):
        """Monitor component health and subscription status."""
        logger.info("STARTED HEALTH CHECK")
        while True:
            try:
                if self.state == ProcessorState.PAUSED:
                    await asyncio.sleep(30)
                    continue

                current_time = datetime.now(timezone.utc)
                if self._last_message_time:
                    time_since_last_message = current_time - self._last_message_time
                    if time_since_last_message > timedelta(minutes=5):
                        logger.warning(f"No messages received for {time_since_last_message}. Checking connection...")
                        await self._reconnect_subscriptions()

                if not self.qm.nc.is_connected:
                    logger.error("NATS connection lost. Attempting to reconnect...")
                    await self.qm.ensure_connected()

                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in health check: {e}")
                await asyncio.sleep(5)

    async def _reconnect_subscriptions(self):
        """Reconnect all subscriptions."""
        try:
            logger.debug("Reconnecting subscriptions...")
            await self.qm.ensure_connected()  # Ensure NATS connection first
            await self._cleanup_subscriptions()
            await self.setup_subscriptions()
            await self.start_pull_processor()  # Restart pull processor after reconnection
            logger.debug("Successfully reconnected subscriptions")
        except Exception as e:
            logger.error(f"Error reconnecting subscriptions: {e}")
            await asyncio.sleep(1)  # Add delay before retry

    async def control_message_handler(self, raw_msg):
        """Handle control messages for component management."""
        logger.debug(f"{self.component_id}: Received control message: {raw_msg.data}")
        try:
            msg = json.loads(raw_msg.data.decode())
            command = msg.get("command")
            target = msg.get("target", "all")
            target_id = msg.get("target_id")

            # Check if message is targeted for this component
            if target not in ["all", self.role] and target != self.component_id:
                logger.debug(f"Ignoring control message - not for this component (target: {target})")
                await raw_msg.ack()
                return

            # For component-specific targeting, check if this is the intended component
            if target == self.role and target_id and target_id != self.component_id:
                logger.debug(f"Ignoring component-specific message - not for this component ID (target_id: {target_id})")
                await raw_msg.ack()
                return

            logger.debug(f"Processing control command: {command}")
            if command == "pause":
                await self._handle_pause_command(msg)
            elif command == "unpause":
                await self._handle_unpause_command(msg)
            elif command == "report":
                await self._handle_report_command(msg)
            elif command == "ping":
                await self._handle_ping_command(msg)
            elif command == "killjob":
                await self._handle_killjob_command(msg)

            await raw_msg.ack()
        except Exception as e:
            logger.error(f"Error in control_message_handler: {e}")
            if not raw_msg._ackd:
                await raw_msg.nak()

    async def _handle_pause_command(self, msg: Dict[str, Any]):
        """Handle pause command."""
        if self.state == ProcessorState.PAUSED:
            await self._send_control_response("pause", "paused", True)
            return

        self.state = ProcessorState.PAUSED
        self.running.clear()
        await self.set_status("paused")
        #logger.info(f"{self.role} {self.component_id} paused")
        await self._send_control_response("pause", "paused", True)

    async def _handle_unpause_command(self, msg: Dict[str, Any]):
        """Handle unpause command."""
        try:
            self.state = ProcessorState.RUNNING
            self.running.set()
            await self.set_status("idle")
            logger.info(f"{self.role} {self.component_id} resumed")
            await self._send_control_response("unpause", "running", True)
        except Exception as e:
            logger.error(f"Error during unpause: {e}")
            await self._send_control_response("unpause", "failed", False)

    async def _handle_report_command(self, msg: Dict[str, Any]):
        """Handle report command."""
        #logger.info("Received report command")
        report = await self.generate_report()
        await self.qm.publish_message(
            subject="function.control.response",
            stream="FUNCTION_CONTROL_RESPONSE",
            message={
                "component_id": self.component_id,
                "type": self.role,
                "command": "report",
                "report": report,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

    async def _handle_ping_command(self, msg: Dict[str, Any]):
        """Handle ping command."""
        logger.info(f"Received ping from {msg.get('target')}")
        await self.qm.publish_message(
            subject="control.response.ping",
            stream="CONTROL_RESPONSE_PING",
            message={
                "component_id": self.component_id,
                "type": self.role,
                "command": "pong",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    @debug_trace
    async def _send_control_response(self, command: str, status: str, success: bool):
        """Send control response message."""
        logger.debug(f"{self.component_id}: Sending control response for {command} with status {status} and success {success}")
        await self.qm.publish_message(
            subject=f"control.response.{command}",
            stream=f"CONTROL_RESPONSE_{command.upper()}",
            message={
                "component_id": self.component_id,
                "type": self.role,
                "status": status,
                "success": success,
                "command": command,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

    async def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive report of the component's current state."""
        try:
            process = psutil.Process()
            cpu_percent = process.cpu_percent(interval=1)
            mem_info = process.memory_info()

            report = {
                "component": {
                    "id": self.component_id,
                    "role": self.role,
                    "version": __version__,
                    "hostname": socket.gethostname(),
                    "state": self.state.value,
                    "uptime": (datetime.now(timezone.utc) - self._start_time).total_seconds(),
                    "last_message_time": self._last_message_time.isoformat() if self._last_message_time else None
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
                        "rss": mem_info.rss,
                        "vms": mem_info.vms,
                        "percent": process.memory_percent()
                    },
                    "threads": process.num_threads()
                },
                "queues": {
                    "nats_connected": self.qm.nc.is_connected if self.qm else False,
                    "subscription": {
                        "active": self._subscription is not None,
                        "sub_key": self._sub_key
                    }
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

    # async def _handle_killjob_command(self, msg: Dict[str, Any]):
    #     """Handle killjob command to cancel running tasks."""
    #     await self._handle_killjob_command(msg)
