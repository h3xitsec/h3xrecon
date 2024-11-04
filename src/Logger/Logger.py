import json
import asyncio
import os
import asyncpg
from nats.aio.client import Client as NATS
from loguru import logger
from datetime import datetime
from typing import Dict, Any

class LoggingService:
    def __init__(self, nats_url: str, db_config: Dict[str, Any]):
        self.nc = NATS()
        self.nats_url = nats_url
        self.db_config = db_config
        self.db_pool = None

    async def connect_nats(self):
        await self.nc.connect(self.nats_url)
        await self.nc.subscribe("logs.general", cb=self.log_handler)
        logger.info("Connected to NATS and subscribed to 'logs.general'")

    async def connect_db(self):
        self.db_pool = await asyncpg.create_pool(**self.db_config)
        logger.info("Connected to the database and ensured 'logs' table exists")

    async def log_handler(self, msg):
        try:
            log_entry = json.loads(msg.data.decode())
            required_fields = {"execution_id", "timestamp", "level", "component", "message"}
            if not required_fields.issubset(log_entry.keys()):
                logger.error("Received log entry with missing fields")
                return

            # Convert timestamp string to datetime object
            timestamp = datetime.fromisoformat(log_entry.get("timestamp"))

            async with self.db_pool.acquire() as connection:
                await connection.execute('''
                    INSERT INTO logs (execution_id, timestamp, level, component, message, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                ''',
                log_entry.get("execution_id"),
                timestamp,
                log_entry.get("level"),
                log_entry.get("component"),
                log_entry.get("message"),
                json.dumps(log_entry.get("metadata", {}))
                )
            logger.debug(f"Inserted log entry: {log_entry['execution_id']}")
        except Exception as e:
            logger.exception(f"Failed to process log entry: {e}")

    async def run(self):
        await self.connect_db()
        await self.connect_nats()
        # Keep the service running
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    db_config = {
        "user": os.getenv("H3XRECON_DB_USER"),
        "password": open('/run/secrets/postgresql_db_password','r').read(),
        "database": os.getenv('H3XRECON_DB_NAME'),
        "host": os.getenv("H3XRECON_DB_HOST"),
        "port": os.getenv("H3XRECON_DB_PORT")
    }
    logging_service = LoggingService(nats_url=f"nats://{os.getenv('H3XRECON_NATS_SERVER')}:{os.getenv('H3XRECON_NATS_PORT')}", db_config=db_config)
    asyncio.run(logging_service.run())