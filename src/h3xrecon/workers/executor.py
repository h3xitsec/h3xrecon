from typing import Dict, Any, AsyncGenerator, List, Callable
from h3xrecon.workers.plugins.base import ReconPlugin
from h3xrecon.core import QueueManager
from h3xrecon.core import DatabaseManager
from loguru import logger
import importlib
import pkgutil
import asyncio
import json
import uuid
from datetime import datetime, timezone

class FunctionExecutor:
    def __init__(self, qm: QueueManager, db: DatabaseManager):
        self.qm = qm
        self.db = db
        self.function_map: Dict[str, Callable] = {}
        self.load_plugins()

    def load_plugins(self):
        """Dynamically load all recon plugins."""
        try:
            package = importlib.import_module('h3xrecon.workers.plugins')
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
                    #logger.debug(f"Checking attribute: {attribute_name}, type: {type(attribute)}")
                    
                    if not isinstance(attribute, type) or not issubclass(attribute, ReconPlugin) or attribute is ReconPlugin:
                       continue
                        
                    plugin_instance = attribute()
                    self.function_map[plugin_instance.name] = plugin_instance.execute
                    logger.info(f"Loaded plugin: {plugin_instance.name}")
                
                
            except Exception as e:
                logger.error(f"Error loading plugin '{module_name}': {e}", exc_info=True)
        logger.debug(f"Current function_map: {[key for key in self.function_map.keys()]}")
    async def execute_function(self, func_name: str, target: str, program_id: int, execution_id: str, timestamp: str, force_execution: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        if func_name not in self.function_map:
            logger.error(f"Function '{func_name}' not found in function_map.")
            return

        plugin_execute = self.function_map[func_name]
        task_sending_functions = ["expand_cidr", "subdomain_permutation"]
        if func_name in task_sending_functions:
            if func_name == "subdomain_permutation":
                # Check if the target is a dns catchall domain
                logger.debug("Checking if the target is a dns catchall domain")
                is_catchall = await self.db.execute_query("SELECT is_catchall FROM domains WHERE domain = $1", target)
                logger.info(is_catchall)
                if is_catchall:
                    logger.info(f"Target {target} is a dns catchall domain, skipping subdomain permutation.")
                    return
                elif is_catchall is None:
                    logger.error(f"Failed to check if target {target} is a dns catchall domain.")
                    return
            async for message in plugin_execute(target=target):
                # Publish each reverse_resolve_ip task
                message["program_id"] = program_id
                message["execution_id"] = execution_id
                #await self.qm.publish_message(subject="function.execute", stream="FUNCTION_EXECUTE", message=message)
                yield message
        else:
            async for result in plugin_execute(target):
                logger.debug(result)
                if isinstance(result, str):
                    result = json.loads(result)
                
                output_data = {
                    "program_id": program_id,
                    "execution_id": execution_id,
                    "source": {"function": func_name, "target": target},
                    "output": result,
                    "timestamp": timestamp
                }
                
                # Publish the result
                await self.qm.publish_message(subject="function.output", stream="FUNCTION_OUTPUT", message=output_data)

                
                yield output_data
