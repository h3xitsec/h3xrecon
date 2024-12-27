from typing import Dict, Any, AsyncGenerator, Callable
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import QueueManager
from h3xrecon.core import DatabaseManager
from h3xrecon.core import Config
from loguru import logger
import importlib
import pkgutil
import redis
from datetime import datetime, timezone
from h3xrecon.core.queue import StreamUnavailableError

class FunctionExecutor():
    def __init__(self, worker_id: str, qm: QueueManager, db: DatabaseManager, config: Config, redis_status: redis.Redis):
        self.worker_id = worker_id
        self.qm = qm
        self.db = db    
        self.config = config
        self.config.setup_logging()
        self.function_map: Dict[str, Callable] = {}
        self.load_plugins()
        self.current_module = None
        self.current_target = None
        self.current_start_time = None
    
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
            
            logger.info(f"LOADED PLUGINS: {', '.join(p.split('.')[-1] for p in plugin_modules)}")
            
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
    
    async def execute_function(self, function_name: str, params: Dict[str, Any], program_id: int, execution_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            # Update current execution info
            self.current_module = function_name
            self.current_target = params.get('target')
            self.current_start_time = datetime.now(timezone.utc)

            plugin = self.function_map.get(function_name)
            if not plugin:
                logger.error(f"Function {function_name} not found")
                raise ValueError(f"Function {function_name} not found")

            logger.debug(f"Running function {function_name} on {params.get('target')} ({execution_id})")
            
            try:
                async for result in plugin(params, program_id, execution_id, self.db):
                    output_data = {
                        "program_id": program_id,
                        "execution_id": execution_id,
                        "source": {
                            "function": function_name,
                            "params": params
                        },
                        "output": result,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # Yield the result first
                    yield output_data
                    
                    # Then attempt to publish it
                    try:
                        await self.qm.publish_message(
                            subject="function.output",
                            stream="FUNCTION_OUTPUT",
                            message=output_data
                        )
                    except StreamUnavailableError as e:
                        logger.warning(f"Stream locked, dropping message: {str(e)}")
                        continue  # Continue with the next result

            except Exception as e:
                logger.error(f"Error executing function {function_name}: {str(e)}")
                logger.exception(e)
                raise
            finally:
                logger.debug(f"Finished running {function_name} on {params.get('target')} ({execution_id})")

        except Exception as e:
            logger.error(f"Error executing function {function_name}: {str(e)}")
            logger.exception(e)
            raise

        finally:
            # Clear current execution info when done
            self.current_module = None
            self.current_target = None
            self.current_start_time = None


