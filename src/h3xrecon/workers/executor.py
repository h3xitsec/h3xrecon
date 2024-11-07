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
            package = importlib.import_module('plugins')
        except ModuleNotFoundError as e:
            logger.error(f"Failed to import 'plugins': {e}")
            return

        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            try:
                module = importlib.import_module(f'plugins.{module_name}')
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, ReconPlugin) and attribute is not ReconPlugin:
                        plugin_instance = attribute()
                        self.function_map[plugin_instance.name] = plugin_instance.execute
                        logger.info(f"Loaded plugin: {plugin_instance.name}")
            except Exception as e:
                logger.error(f"Error loading plugin '{module_name}': {e}")

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
