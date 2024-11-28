import os
import sys
from loguru import logger
from .executor import FunctionExecutor
from h3xrecon.core import QueueManager
from h3xrecon.core import DatabaseManager
from h3xrecon.core import Config
from h3xrecon.__about__ import __version__
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import redis

class Worker:
    def __init__(self, config: Config):
        self.qm = QueueManager(config.nats)
        self.db = DatabaseManager() #config.database.to_dict() )
        self.config = config
        self.config.setup_logging()
        self.worker_id = f"worker-{os.getenv('HOSTNAME')}"
        self.function_executor = FunctionExecutor(qm=self.qm, db=self.db, config=self.config)
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.redis_client = redis.Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password
        )

    async def start(self):
        logger.info(f"Starting worker (Worker ID: {self.worker_id})...")
        
        try:
            await self.qm.connect()
            await self.qm.subscribe(
                subject="function.execute",
                stream="FUNCTION_EXECUTE",
                durable_name="MY_CONSUMER",
                message_handler=self.message_handler,
                batch_size=1
            )
            logger.info(f"Worker {self.worker_id} listening for messages...")
        except ConnectionError as e:
            logger.error(str(e))
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to start worker: {str(e)}")
            sys.exit(1)

    async def should_execute(self, msg) -> bool:
        data = msg
        redis_key = f"{data.get('function')}:{data.get('params', {}).get('target')}"
        last_execution = self.redis_client.get(redis_key)
        if last_execution:
            last_execution_time = datetime.fromisoformat(last_execution.decode())
            time_since_last_execution = datetime.now(timezone.utc) - last_execution_time
            skip = not time_since_last_execution > self.execution_threshold
            if skip:
                logger.info(f"Skipping {data.get('function')} on {data.get('params', {}).get('target')} : executed recently.")
            else:
                logger.info(f"Running {data.get('function')} on {data.get('params', {}).get('target')} ({data.get('execution_id')})")
            return not skip
        return True

    async def message_handler(self, msg):
        try:
            if not msg.get("force", False):
                if not await self.should_execute(msg):
                    return
            
            execution_id = msg.get("execution_id", str(uuid.uuid4()))

            async for result in self.function_executor.execute_function(
                    func_name=msg["function"],
                    params=msg["params"],
                    program_id=msg["program_id"],
                    execution_id=execution_id,
                    timestamp=msg.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    force_execution=msg.get("force_execution", False)
                ):
                pass
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.exception(e)
            #raise  # Let process_messages handle the error

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
        logger.info("Worker shutdown complete")

def run():
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())