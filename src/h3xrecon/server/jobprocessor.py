from h3xrecon.core import DatabaseManager
from h3xrecon.core import QueueManager
from h3xrecon.core import Config
from h3xrecon.plugins import ReconPlugin
from h3xrecon.__about__ import __version__

from typing import Dict, Any, Callable, List
from loguru import logger
from dataclasses import dataclass
import json
import os
import traceback
import importlib
import pkgutil
import redis
import asyncio

from uuid import UUID
from datetime import datetime

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

class JobProcessor:
    def __init__(self, config: Config):
        self.db = DatabaseManager()
        self.qm = QueueManager(config.nats)
        self.jobprocessor_id = f"jobprocessor-{os.getenv('HOSTNAME')}"
        self.processor_map: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        redis_config = config.redis
        self.redis_client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password
        )
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

    async def start(self):
        logger.info(f"Starting Job Processor (ID: {self.jobprocessor_id}) version {__version__}...")
        await self.qm.connect()
        await self.qm.subscribe(
            subject="function.output",
            stream="FUNCTION_OUTPUT",
            durable_name="MY_CONSUMER",
            message_handler=self.message_handler,
            batch_size=1
        )

    async def stop(self):
        logger.info("Shutting down...")

    async def message_handler(self, msg):
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
            
        except (KeyError, ValueError, TypeError) as e:
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            file_name = error_location.filename.split('/')[-1]
            line_number = error_location.lineno
            logger.error(f"Error in {file_name}:{line_number} - {type(e).__name__}: {str(e)}")
    
    async def log_or_update_function_execution(self, message_data: Dict[str, Any], execution_id: str, timestamp: str):
        try:
            log_entry = {
                "execution_id": execution_id,
                "timestamp": timestamp,
                "function_name": message_data.get("source", {}).get("params", {}).get("function", "unknown"),
                "target": message_data.get("source", {}).get("params", {}).get("target", "unknown"),
                "program_id": message_data.get("program_id"),
                "results": message_data.get("data", [])
            }
            if not message_data.get("nolog", False):
                await self.db.log_or_update_function_execution(log_entry)

            # Update Redis with the last execution timestamp
            function_name = message_data.get("source", {}).get("function", "unknown")
            target = message_data.get("source", {}).get("params", {}).get("target", "unknown")
            redis_key = f"{function_name}:{target}"
            self.redis_client.set(redis_key, timestamp)
        except Exception as e:
            logger.error(f"Error logging or updating function execution: {e}")

    async def process_function_output(self, msg_data: Dict[str, Any]):
        function_name = msg_data.get("source", {}).get("function")
        if function_name in self.processor_map:
            logger.info(f"Processing output from plugin '{function_name}' on target '{msg_data.get('source', {}).get('params', {}).get('target')}'")
            try:
                await self.processor_map[function_name](msg_data, self.db)
            except Exception as e:
                logger.error(f"Error processing output with plugin '{function_name}': {e}", exc_info=True)
        else:
            logger.warning(f"No processor found for function: {function_name}")

    #############################################
    ## Recon tools output processing functions ##
    #############################################
    
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
