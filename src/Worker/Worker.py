import os
import sys
from loguru import logger
from FunctionExecutor import FunctionExecutor
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import redis
from QueueManager import QueueManager
from DatabaseManager import DatabaseManager


class Worker:
    def __init__(self):
        self.qm = QueueManager()
        self.db = DatabaseManager()
        self.worker_id = f"worker-{os.getenv('HOSTNAME')}"
        self.function_executor = None
        self.execution_threshold = timedelta(hours=24)
        self.result_publisher = None
        self.redis_client = redis.Redis(
            host=os.getenv('H3XRECON_REDIS_SERVER', 'redis'),
            port=int(os.getenv('H3XRECON_REDIS_PORT', 6379)),
            db=0
        )

    async def start(self):
        logger.info(f"Starting worker (Worker ID: {self.worker_id})...")
        self.function_executor = FunctionExecutor(qm=self.qm, db=self.db)
        logger.info(f"Worker {self.worker_id} listening for messages...")
        
        await self.qm.connect()
        await self.qm.subscribe(
            subject="function.execute",
            stream="FUNCTION_EXECUTE",
            durable_name="MY_CONSUMER",
            message_handler=self.message_handler,
            batch_size=1
        )

    async def should_execute(self, msg) -> bool:
        data = msg
        redis_key = f"{data.get('function')}:{data.get('params', {}).get('target')}"
        last_execution = self.redis_client.get(redis_key)
        if last_execution:
            last_execution_time = datetime.fromisoformat(last_execution.decode())
            time_since_last_execution = datetime.now(timezone.utc) - last_execution_time
            skip = not time_since_last_execution > self.execution_threshold
            if skip:
                logger.info(f"Skipping execution of {data.get('function')} on {data.get('params', {}).get('target')} as it was executed recently.")
            else:
                logger.info(f"Executing {data.get('function')} on {data.get('params', {}).get('target')} ({data.get('execution_id')})")
            return not skip
        return True

    async def message_handler(self, msg):
        #logger.debug(f"Incoming message:\nObject Type: {type(msg)}\nObject:\n{json.dumps(msg, indent=4)}")
        try:
            if not msg.get("force", False):
                if not await self.should_execute(msg):
                    return
            logger.info(f"Processing function: {msg.get('function')} for target: {msg.get('params', {}).get('target')}")
            
            execution_id = msg.get("execution_id", str(uuid.uuid4()))
            
            async for result in self.function_executor.execute_function(
                    func_name=msg["function"],
                    target=msg["params"]["target"],
                    program_id=msg["program_id"],
                    execution_id=execution_id,
                    timestamp=msg.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    force_execution=msg.get("force_execution", False)
                ):
                pass
                #logger.debug(f"Function execution result: {result}")
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.exception(e)
            #raise  # Let process_messages handle the error

    async def stop(self):
        logger.info("Shutting down...")

async def main():
    worker = Worker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()

if __name__ == "__main__":
    # Configure logger
    logger.remove()
    logger.add(sys.stdout, level="DEBUG", format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    
    asyncio.run(main())
