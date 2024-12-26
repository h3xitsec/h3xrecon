from h3xrecon.core.component import ReconComponent, ProcessorState
from h3xrecon.plugins import ReconPlugin
from h3xrecon.__about__ import __version__
from h3xrecon.core.utils import debug_trace
from h3xrecon.core import Config
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from datetime import datetime, timezone
from typing import Dict, Any, Callable, List
from loguru import logger
from dataclasses import dataclass
import importlib
import pkgutil
import json
import uuid
import traceback
import asyncio
import sys
from uuid import UUID

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

class JobProcessor(ReconComponent):
    def __init__(self, config: Config):
        super().__init__("jobprocessor", config)
        self.processor_map: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._load_plugins()

    def _load_plugins(self):
        """Load all available plugins."""
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

    async def setup_subscriptions(self):
        """Setup NATS subscriptions for the job processor."""
        try:
            async with self._subscription_lock:
                if self.state == ProcessorState.PAUSED:
                    logger.debug("Job processor is paused, skipping subscription setup")
                    return

                # Clean up existing subscriptions using parent class method
                await self._cleanup_subscriptions()

                subscription = await self.qm.subscribe(
                    subject="function.output",
                    stream="FUNCTION_OUTPUT",
                    durable_name=f"JOBPROCESSORS_{self.component_id}",  # Make durable name unique
                    message_handler=self.message_handler,
                    batch_size=1,
                    queue_group="jobprocessors",
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT,
                        'max_deliver': 1,
                        'max_ack_pending': 1000,
                        'flow_control': False,
                        'deliver_group': 'jobprocessors'
                    },
                    pull_based=True
                )
                self._subscription = subscription
                self._sub_key = f"FUNCTION_OUTPUT:function.output:JOBPROCESSORS_{self.component_id}"
                logger.info("Successfully subscribed to output channel")

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
                    subject=f"function.control.all_jobprocessor",
                    stream="FUNCTION_CONTROL",
                    durable_name=f"CONTROL_ALL_JOBPROCESSOR_{self.component_id}",
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
            logger.error(f"Error setting up job processor subscriptions: {e}")
            raise

    async def message_handler(self, raw_msg):
        """Handle incoming function output messages."""
        msg = json.loads(raw_msg.data.decode())
        if self.state == ProcessorState.PAUSED:
            await raw_msg.nak()
            return

        try:
            # Validate the message using FunctionExecution dataclass
            function_execution = FunctionExecution(
                execution_id=msg['execution_id'],
                timestamp=msg['timestamp'],
                program_id=msg['program_id'],
                source=msg['source'],
                output=msg.get('data', [])
            )
            
            # Log or update function execution in database
            await self.log_or_update_function_execution(msg, function_execution.execution_id, function_execution.timestamp)
            function_name = function_execution.source.get("function")
            if function_name:
                await self.process_function_output(msg)
                await raw_msg.ack()
            else:
                logger.error(f"No function name found in message: {msg}")
                await raw_msg.nak()
            
        except (KeyError, ValueError, TypeError) as e:
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            file_name = error_location.filename.split('/')[-1]
            line_number = error_location.lineno
            logger.error(f"Error in {file_name}:{line_number} - {type(e).__name__}: {str(e)}")
        finally:
            if not raw_msg._ackd:
                await raw_msg.ack()
            await self.set_status("running")

    async def log_or_update_function_execution(self, message_data: Dict[str, Any], execution_id: str, timestamp: str):
        """Log or update function execution in the database."""
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
        """Process the output from a function execution."""
        function_name = msg_data.get("source", {}).get("function")
        if function_name in self.processor_map:
            logger.info(f"Processing output from plugin '{function_name}' on target '{msg_data.get('source', {}).get('params', {}).get('target')}'")
            try:
                await self.processor_map[function_name](msg_data, self.db, self.qm)
            except Exception as e:
                logger.error(f"Error processing output with plugin '{function_name}': {e}")
                raise
        else:
            logger.warning(f"No processor found for function: {function_name}")

async def main():
    config = Config()
    config.setup_logging()
    logger.info(f"Starting H3XRecon job processor... (v{__version__})")

    job_processor = JobProcessor(config)
    try:
        await job_processor.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down job processor...")
        await job_processor.stop()
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        sys.exit(1)

def run():
    asyncio.run(main())

if __name__ == "__main__":
    run()
