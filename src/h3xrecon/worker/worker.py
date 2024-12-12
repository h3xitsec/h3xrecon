import socket
import sys
from loguru import logger
from h3xrecon.worker.executor import FunctionExecutor
from h3xrecon.core import QueueManager
from h3xrecon.core import DatabaseManager
from h3xrecon.core import Config
from h3xrecon.__about__ import __version__

from dataclasses import dataclass
from typing import Dict, Any, Optional
import importlib
import pkgutil
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import redis
import time

@dataclass
class FunctionExecutionRequest:
    function_name: str
    program_id: int
    params: Dict[str, Any]
    force: bool
    execution_id: Optional[str] = str(uuid.uuid4())
    timestamp: Optional[str] = datetime.now(timezone.utc).isoformat()

class Worker:
    def __init__(self, config: Config):
        self.qm = QueueManager(config.nats)
        self.db = DatabaseManager() #config.database.to_dict() )
        self.config = config
        self.config.setup_logging()
        self.worker_id = f"worker-{socket.gethostname()}"
        logger.debug(f"Redis config: {config.redis}")
        self.redis_status = self._init_redis_with_retry(
            host=config.redis.host,
            port=config.redis.port,
            db=1,
            password=config.redis.password
        )
        self.function_executor = FunctionExecutor(worker_id=self.worker_id, qm=self.qm, db=self.db, config=self.config, redis_status=self.redis_status)
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.redis_cache = redis.Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password
        )
        

    def _init_redis_with_retry(self, host, port, db, password, max_retries=20, retry_delay=5):
        for attempt in range(max_retries):
            try:
                redis_client = redis.Redis(host=host, port=port, db=db, password=password)
                # Test the connection
                redis_client.ping()
                logger.info(f"Successfully connected to Redis on attempt {attempt + 1}")
                return redis_client
            except (redis.ConnectionError, redis.TimeoutError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to connect to Redis after {max_retries} attempts")
                    raise
                logger.warning(f"Failed to connect to Redis (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)

    async def validate_function_execution_request(self, function_execution_request: FunctionExecutionRequest) -> bool:
        # Validate function_name is a valid plugin
        try:
            # Dynamically import plugins to check if the function_name is valid
            plugin_found = False
            
            # Check if the function name exists in the function map keys
            plugin_found = any(function_execution_request.function_name in key for key in self.function_executor.function_map.keys())
            
            if not plugin_found:
                logger.debug(f"Invalid function_name: {function_execution_request.function_name}. No matching plugin found in {list(self.function_executor.function_map.keys())}")
                raise ValueError(f"Invalid function_name: {function_execution_request.function_name}. No matching plugin found.")
        
        except Exception as e:
            raise ValueError(f"Error validating function_name: {str(e)}")
        
        # Validate program_name exists in the database
        try:
            program_name = await self.db.get_program_name(function_execution_request.program_id)
            if not program_name:
                raise ValueError(f"Invalid program_id: {function_execution_request.program_id}. Program not found in database.")
        
        except Exception as e:
            raise ValueError(f"Error validating program_name: {str(e)}")

    async def start(self):
        logger.info(f"Starting Worker (Worker ID: {self.worker_id}) version {__version__}...")
        try:
            # Test Redis connection first
            try:
                self.redis_status.ping()
            except (redis.ConnectionError, redis.TimeoutError) as e:
                raise ConnectionError(f"Cannot connect to Redis: {e}")

            await self.qm.connect()
            await self.qm.subscribe(
                subject="function.execute",
                stream="FUNCTION_EXECUTE",
                durable_name="MY_CONSUMER",
                message_handler=self.message_handler,
                batch_size=1
            )
            logger.info(f"Worker {self.worker_id} started and listening for messages...")
        except ConnectionError as e:
            logger.error(str(e))
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to start worker: {str(e)}")
            sys.exit(1)

    async def should_execute(self, function_execution_request: FunctionExecutionRequest) -> bool:
        data = function_execution_request
        redis_key = f"{data.function_name}:{data.params.get('target')}"
        last_execution = self.redis_cache.get(redis_key)
        if last_execution:
            last_execution_time = datetime.fromisoformat(last_execution.decode())
            time_since_last_execution = datetime.now(timezone.utc) - last_execution_time
            skip = not time_since_last_execution > self.execution_threshold
            if skip:
                logger.info(f"Skipping {data.function_name} on {data.params.get('target')} : executed recently.")
            return not skip
        return True

    async def message_handler(self, msg):
        try:
            logger.debug(msg)
            function_execution_request = FunctionExecutionRequest(
                program_id=msg.get('program_id'),
                function_name=msg.get('function'),
                params=msg.get('params'),
                force=msg.get("force", False)
            )
            await self.validate_function_execution_request(function_execution_request)
            if not function_execution_request.force:
                if not await self.should_execute(function_execution_request):
                    return
            
            async for result in self.function_executor.execute_function(
                    func_name=function_execution_request.function_name,
                    params=function_execution_request.params,
                    program_id=function_execution_request.program_id,
                    execution_id=function_execution_request.execution_id,
                    timestamp=function_execution_request.timestamp,
                    force_execution=function_execution_request.force
                ):
                pass
        except ValueError as e:
            logger.error(f"{e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.exception(e)

    async def stop(self):
        logger.info("Shutting down...")

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
        worker.redis_status.delete(worker.worker_id)
        logger.info("Worker shutdown complete")

def run():
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())