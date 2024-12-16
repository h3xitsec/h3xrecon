from typing import Dict, Any, AsyncGenerator, Callable
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import QueueManager
from h3xrecon.core import DatabaseManager
from h3xrecon.core import Config
from loguru import logger
import importlib
import pkgutil
import json
import redis
import asyncio
from datetime import datetime, timezone

class FunctionExecutor():
    def __init__(self, worker_id: str, qm: QueueManager, db: DatabaseManager, config: Config, redis_status: redis.Redis):
        self.worker_id = worker_id
        self.qm = qm
        self.db = db    
        self.config = config
        self.config.setup_logging()
        self.function_map: Dict[str, Callable] = {}
        self.load_plugins()
        self.redis_status = redis_status
        self.set_status("idle")

    def set_status(self, status: str):
        self.redis_status.set(self.worker_id, status)
    
    def load_plugins(self):
        """Dynamically load all recon plugins."""
        try:
            package = importlib.import_module('h3xrecon.plugins.plugins')
            logger.debug(f"Found plugin package at: {package.__path__}")
            
            # Walk through all subdirectories
            plugin_modules = []
            for finder, name, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
                if not name.endswith('.base'):  # Skip the base module
                    plugin_modules.append(name)
            
            logger.info(f"Loaded plugins: {plugin_modules}")
            
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
                    bound_method = plugin_instance.execute
                    self.function_map[plugin_instance.name] = bound_method
                    logger.debug(f"Loaded plugin: {plugin_instance.name} with timeout: {plugin_instance.timeout}s")
                
            except Exception as e:
                logger.error(f"Error loading plugin '{module_name}': {e}", exc_info=True)
        logger.debug(f"Current function_map: {[key for key in self.function_map.keys()]}")
    
    async def execute_function(self, 
                              func_name: str, 
                              params: Dict[str, Any], 
                              program_id: int, 
                              execution_id: str, 
                              timestamp: str, 
                              force_execution: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        if func_name not in self.function_map:
            logger.error(f"Function '{func_name}' not found in function_map.")
            return

        # Get the plugin instance
        plugin_instance = next(p for p in self.function_map.values() if p.__self__.name == func_name)
        plugin_timeout = plugin_instance.__self__.timeout
        plugin_execute = self.function_map[func_name]
        self.set_status(f"{func_name}__{params.get('target')}__{execution_id}")

        try:
            async with asyncio.timeout(plugin_timeout):
                async for result in plugin_execute(params, program_id, execution_id):
                    try:
                        # Check if the task has been cancelled
                        await asyncio.sleep(0)  # Allow cancellation to propagate
                        if asyncio.current_task().cancelled():
                            raise asyncio.CancelledError()
                    except asyncio.CancelledError:
                        logger.info(f"Execution {execution_id} received cancellation signal.")
                        raise

                    if isinstance(result, str):
                        result = json.loads(result)
                    output_data = {
                        "program_id": program_id,
                        "execution_id": execution_id,
                        "source": {"function": func_name, "params": params, "force": force_execution},
                        "output": result,
                        "timestamp": timestamp
                    }
                    # Publish the result
                    await self.qm.publish_message(subject="function.output", stream="FUNCTION_OUTPUT", message=output_data)
                    yield output_data

        except asyncio.TimeoutError:
            logger.error(f"Function '{func_name}' timed out after {plugin_timeout} seconds")
            error_data = {
                "program_id": program_id,
                "execution_id": execution_id,
                "source": {"function": func_name, "params": params, "force": force_execution},
                "output": {"error": f"Function timed out after {plugin_timeout} seconds"},
                "timestamp": timestamp
            }
            await self.qm.publish_message(subject="function.output", stream="FUNCTION_OUTPUT", message=error_data)
            yield error_data
        except asyncio.CancelledError:
            logger.info(f"Function '{func_name}' execution was cancelled.")
            # Optionally, handle cleanup here or publish cancellation status
            # cancel_data = {
            #     "program_id": program_id,
            #     "execution_id": execution_id,
            #     "source": {"function": func_name, "params": params, "force": force_execution},
            #     "output": {"error": "Function execution was cancelled."},
            #     "timestamp": datetime.now(timezone.utc).isoformat()
            # }
            # try:
            #     await self.qm.publish_message(subject="function.output", stream="FUNCTION_OUTPUT", message=cancel_data)
            #     yield cancel_data
            # except Exception as e:
            #     logger.error(f"Failed to publish cancellation message: {e}")
            # raise  # Re-raise to allow the caller to handle the cancellation
        except Exception as e:
            logger.error(f"Error executing function '{func_name}': {e}")
            self.set_status("idle")
            raise
        finally:
            self.set_status("idle")
            logger.info(f"Finished running {func_name} on {params.get('target')} ({execution_id})")


