from h3xrecon.core import DatabaseManager
from h3xrecon.core import QueueManager
from h3xrecon.core import Config
from h3xrecon.core.queue import StreamUnavailableError
from h3xrecon.plugins import ReconPlugin
from h3xrecon.__about__ import __version__
from h3xrecon.core.preflight import PreflightCheck
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Callable, List
from loguru import logger
from dataclasses import dataclass
import socket
import traceback
import importlib
import pkgutil
import redis
import asyncio
import sys

from uuid import UUID
from datetime import datetime
from enum import Enum
import json
import psutil
import platform

@dataclass
class FunctionExecution:
    execution_id: str
    timestamp: str
    program_id: int
    source: Dict[str, Any]
    output: List[Dict[str, Any]]

    def __post_init__(self):
        # Validate execution_id is a valid UUID
        try:
            UUID(self.execution_id)
        except ValueError:
            logger.error("execution_id must be a valid UUID")
            raise ValueError("execution_id must be a valid UUID")

        # Validate timestamp is a valid timestamp
        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError:
            logger.error("timestamp must be a valid ISO format timestamp")
            raise ValueError("timestamp must be a valid ISO format timestamp")

        # Validate program_id is an integer
        try:
            int(self.program_id)
        except ValueError:
            logger.error("program_id must be an integer")
            raise ValueError("program_id must be an integer")

        # Validate source is a dictionary
        if not isinstance(self.source, dict):
            logger.error("source must be a dictionary")
            raise TypeError("source must be a dictionary")

        # Validate output is a list
        if not isinstance(self.output, list):
            logger.error("output must be a list")
            raise TypeError("output must be a list")

class ProcessorState(Enum):
    RUNNING = "running"
    PAUSED = "paused"

class JobProcessor:
    def __init__(self, config: Config):
        self.config = config
        self.db = DatabaseManager()
        self.qm = QueueManager(client_name="jobprocessor", config=config.nats)
        self.jobprocessor_id = f"jobprocessor-{socket.gethostname()}"
        self.processor_map: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        redis_config = config.redis
        self.redis_cache = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password
        )
        # Connect to the status redis db to flush all worker statuses
        self.redis_status = redis.Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=1,
            password=config.redis.password
        )
        self.state = ProcessorState.RUNNING
        self.control_subscription = None
        self.output_subscription = None
        try:
            package = importlib.import_module('h3xrecon.plugins.plugins')
            logger.debug(f"Found plugin package at: {package.__path__}")
            
            # Walk through all subdirectories
            plugin_modules = []
            for finder, name, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
                if not name.endswith('.base'):  # Skip the base module
                    plugin_modules.append(name)
            
            logger.debug(f"Discovered modules: {plugin_modules}")
            
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
                    logger.debug(f"Loaded plugin: {plugin_instance.name}")
                    
                    if not hasattr(plugin_instance, 'process_output') or not callable(getattr(plugin_instance, 'process_output')):
                        logger.warning(f"Plugin '{plugin_instance.name}' does not have a callable 'process_output' method.")
                        continue
                    
                    self.processor_map[plugin_instance.name] = plugin_instance.process_output
            except Exception as e:
                logger.warning(f"Error loading plugin '{module_name}': {e}", exc_info=True)

        self._last_message_time = None
        self._health_check_task = None

    async def _setup_subscription(self, subject: str, stream: str, message_handler: Callable, 
                                broadcast: bool = False, queue_group: str = None):
        """Helper method to setup NATS subscriptions with consistent configuration."""
        subscription = await self.qm.subscribe(
            subject=subject,
            stream=stream,
            message_handler=message_handler,
            batch_size=1,
            consumer_config={
                'ack_policy': AckPolicy.EXPLICIT,
                'deliver_policy': DeliverPolicy.ALL,
                'replay_policy': ReplayPolicy.INSTANT
            },
            queue_group=queue_group,
            broadcast=broadcast
        )
        return subscription

    async def start(self):
        logger.info(f"Starting Job Processor (ID: {self.jobprocessor_id}) version {__version__}...")
        try:
            # Run preflight checks
            preflight = PreflightCheck(self.config, f"jobprocessor-{self.jobprocessor_id}")
            if not await preflight.run_checks():
                raise ConnectionError("Preflight checks failed. Cannot start job processor.")

            # Initialize components with retry logic
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                try:
                    await self.qm.connect()
                    # Store the subscription object
                    self.output_subscription = await self._setup_subscription(
                        subject="function.output",
                        stream="FUNCTION_OUTPUT",
                        message_handler=self.message_handler,
                        queue_group="jobprocessor"
                    )
                    logger.info(f"Job Processor started and listening for messages...")
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        raise e
                    await asyncio.sleep(1)

            # Add control message subscription
            await self._setup_subscription(
                subject="function.control",
                stream="FUNCTION_CONTROL",
                message_handler=self.control_message_handler,
                broadcast=True
            )

            # Start health check
            self._health_check_task = asyncio.create_task(self._health_check())
        except Exception as e:
            logger.error(f"Failed to start job processor: {str(e)}")
            sys.exit(1)

    async def stop(self):
        logger.info("Shutting down...")

    async def message_handler(self, msg):
        if self.state == ProcessorState.PAUSED:
            logger.debug("Processor is paused, skipping message")
            await msg.nack()
            return

        try:
            # Validate the message using FunctionExecution dataclass
            data = json.loads(msg.data.decode())
            function_execution = FunctionExecution(
                execution_id=data['execution_id'],
                timestamp=data['timestamp'],
                program_id=data['program_id'],
                source=data['source'],
                output=data.get('data', [])
            )
            
            # Log or update function execution in database
            await self.log_or_update_function_execution(data, function_execution.execution_id, function_execution.timestamp)
            function_name = function_execution.source.get("function")
            if function_name:
                await self.process_function_output(data)
                msg.ack()
            else:
                logger.error(f"No function name found in message: {data}")
                await msg.nack()
            
        except (KeyError, ValueError, TypeError) as e:
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            file_name = error_location.filename.split('/')[-1]
            line_number = error_location.lineno
            logger.error(f"Error in {file_name}:{line_number} - {type(e).__name__}: {str(e)}")
    
    async def log_or_update_function_execution(self, message_data: Dict[str, Any], execution_id: str, timestamp: str):
        try:
            # Extract function parameters
            params = message_data.get("source", {}).get("params", {})
            function_name = message_data.get("source", {}).get("function", "unknown")
            target = params.get("target", "unknown")
            
            logger.debug(f"Original params in jobprocessor: {params}")
            
            # Handle extra_params specially if it exists as a list
            if 'extra_params' in params and isinstance(params['extra_params'], list):
                extra_params_str = f"extra_params={sorted(params['extra_params'])}"
                logger.debug(f"Using list extra_params in jobprocessor: {extra_params_str}")
            else:
                # Create a sorted, filtered copy of params excluding certain keys
                extra_params = {k: v for k, v in sorted(params.items()) 
                               if k not in ['target', 'force'] and not k.startswith('--')}
                # Convert extra_params to a string representation
                extra_params_str = ':'.join(f"{k}={v}" for k, v in extra_params.items()) if extra_params else ''
                logger.debug(f"Using dict extra_params in jobprocessor: {extra_params_str}")
            
            # Construct Redis key with extra parameters
            redis_key = f"{function_name}:{target}"
            if extra_params_str:
                redis_key = f"{redis_key}:{extra_params_str}"
            
            logger.debug(f"Setting Redis key in jobprocessor: {redis_key}")
            
            log_entry = {
                "execution_id": execution_id,
                "timestamp": timestamp,
                "function_name": function_name,
                "target": target,
                "program_id": message_data.get("program_id"),
                "results": message_data.get("data", [])
            }
            
            if not message_data.get("nolog", False):
                await self.db.log_or_update_function_execution(log_entry)

            # Update Redis with the last execution timestamp
            logger.debug(f"Setting Redis key: {redis_key} with timestamp: {timestamp}")
            self.redis_cache.set(redis_key, timestamp)
        except Exception as e:
            logger.error(f"Error logging or updating function execution: {e}")

    async def process_function_output(self, msg_data: Dict[str, Any]):
        function_name = msg_data.get("source", {}).get("function")
        if function_name in self.processor_map:
            logger.info(f"Processing output from plugin '{function_name}' on target '{msg_data.get('source', {}).get('params', {}).get('target')}'")
            try:
                try:
                    await self.processor_map[function_name](msg_data, self.db, self.qm)
                except StreamUnavailableError as e:
                    logger.error(f"Failed to process output - stream unavailable: {str(e)}")
                    # Optionally store failed outputs for retry
                    # await self.store_failed_output(msg_data)
                except Exception as e:
                    logger.error(f"Error processing output with plugin '{function_name}': {e}")
                    logger.exception(e)
                    raise
            except Exception as e:
                logger.error(f"Error in output processor for '{function_name}': {e}")
                logger.exception(e)
        else:
            logger.warning(f"No processor found for function: {function_name}")

    #############################################
    ## Recon tools output processing functions ##
    #############################################
    
    async def _health_check(self):
        """Monitor processor health and subscription status."""
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                if self._last_message_time:
                    time_since_last_message = current_time - self._last_message_time
                    if time_since_last_message > timedelta(minutes=5):
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
            await self.qm.connect()
            self.output_subscription = await self._setup_subscription(
                subject="function.output",
                stream="FUNCTION_OUTPUT",
                message_handler=self.message_handler,
                queue_group="jobprocessor"
            )
            logger.info("Successfully reconnected subscriptions")
        except Exception as e:
            logger.error(f"Error reconnecting subscriptions: {e}")

    async def control_message_handler(self, raw_msg):
        """Handle control messages for pausing/unpausing the processor"""
        try:
            msg = json.loads(raw_msg.data.decode())
            command = msg.get("command")
            target = msg.get("target", "all")
            
            if target not in ["all", "jobprocessor"]:
                return

            if command == "pause":
                logger.info("Received pause command")
                self.state = ProcessorState.PAUSED
                
                # Properly unsubscribe if we have an active subscription
                if self.output_subscription:
                    try:
                        await self.output_subscription.unsubscribe()
                        self.output_subscription = None
                        logger.info("Successfully unsubscribed from function.output")
                    except Exception as e:
                        logger.error(f"Error unsubscribing from function.output: {e}")
                
                # Send acknowledgment
                await self.qm.publish_message(
                    subject="function.control.response",
                    stream="FUNCTION_CONTROL_RESPONSE",
                    message={
                        "processor_id": self.jobprocessor_id,
                        "type": "jobprocessor",
                        "status": "paused",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            
            elif command == "unpause":
                logger.info("Received unpause command")
                self.state = ProcessorState.RUNNING
                
                # Only attempt to resubscribe if we're not already subscribed
                if not self.output_subscription:
                    try:
                        self.output_subscription = await self._setup_subscription(
                            subject="function.output",
                            stream="FUNCTION_OUTPUT",
                            message_handler=self.message_handler,
                            queue_group="jobprocessor"
                        )
                        logger.info("Successfully resubscribed to function.output")
                    except Exception as e:
                        logger.error(f"Error resubscribing to function.output: {e}")
                        return
                
                # Send acknowledgment
                await self.qm.publish_message(
                    subject="function.control.response",
                    stream="FUNCTION_CONTROL_RESPONSE",
                    message={
                        "processor_id": self.jobprocessor_id,
                        "type": "jobprocessor",
                        "status": "running",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )

            elif command == "report":
                logger.info("Received report command")
                report = await self.generate_report()
                logger.debug(f"Report: {report}")
                # Send report through control response channel
                await self.qm.publish_message(
                    subject="function.control.response",
                    stream="FUNCTION_CONTROL_RESPONSE",
                    message={
                        "processor_id": self.jobprocessor_id,
                        "type": "jobprocessor",
                        "command": "report",
                        "report": report,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                logger.debug("Job processor report sent")
            await raw_msg.ack()
        except Exception as e:
            logger.error(f"Error handling control message: {e}")
            await raw_msg.nack()

    async def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive report of the job processor's current state."""
        try:
            # Get process info
            process = psutil.Process()
            cpu_percent = process.cpu_percent(interval=1)
            mem_info = process.memory_info()
            
            report = {
                "processor": {
                    "id": self.jobprocessor_id,
                    "version": __version__,
                    "hostname": socket.gethostname(),
                    "state": self.state.value,
                    "uptime": (datetime.now(timezone.utc) - self._start_time).total_seconds() if hasattr(self, '_start_time') else None,
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
                    "output_subscription": {
                        "active": self.output_subscription is not None,
                        "queue_group": "jobprocessor"
                    },
                    "control_subscription": {
                        "active": self.control_subscription is not None
                    }
                },
                "plugins": {
                    "registered_processors": list(self.processor_map.keys())
                },
                "redis": {
                    "cache_connection": bool(self.redis_cache.ping() if self.redis_cache else False),
                    "status_connection": bool(self.redis_status.ping() if self.redis_status else False)
                }
            }
            
            return report
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return {"error": str(e)}

async def main():
    config = Config()
    config.setup_logging()
    job_processor = JobProcessor(config)
    await job_processor.start()
    
    try:
        # Keep the data processor running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await job_processor.stop()

def run():
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
