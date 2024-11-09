import json
import asyncio
import os
import asyncpg
from nats.aio.client import Client as NATS
from loguru import logger
from datetime import datetime
from typing import Dict, Any
from h3xrecon.core.config import Config
from h3xrecon.core.database import DatabaseManager
from h3xrecon.core.queue import QueueManager

class LoggingService:
    def __init__(self, config: Config):
        self.qm = QueueManager(config.nats)
        self.db_manager = DatabaseManager(config.database.to_dict())
        self.db_pool = None

    async def connect_nats(self):
        await self.qm.connect()
        await self.qm.subscribe(
            subject="logs.general",
            stream="LOGS_GENERAL",
            durable_name="MY_CONSUMER",
            message_handler=self.message_handler,
            batch_size=1
        )
        logger.info("Connected to NATS and subscribed to 'logs.general'")

    async def connect_db(self):
        await self.db_manager.connect()
        logger.info("Connected to the database and ensured 'logs' table exists")

    async def log_message(self, log_entry: Dict[str, Any]):
        logger.debug(f"Logging message: {log_entry}")
        # Convert timestamp string to datetime object
        timestamp = datetime.fromisoformat(log_entry.get("timestamp"))
        await self.db_manager.execute_query('INSERT INTO logs (execution_id, timestamp, level, component, message, metadata) VALUES ($1, $2, $3, $4, $5, $6)',
            log_entry.get("execution_id"),
            timestamp,
            log_entry.get("level"),
            log_entry.get("component"),
            log_entry.get("message"),
            json.dumps(log_entry.get("metadata", {}))
            )
        logger.debug(f"Inserted log entry: {log_entry['execution_id']}")


    async def message_handler(self, msg):
        try:
            log_entry = json.loads(msg.data.decode())
            required_fields = {"execution_id", "timestamp", "level", "component", "message"}
            if not required_fields.issubset(log_entry.keys()):
                logger.error("Received log entry with missing fields")
                return
            await self.log_message(log_entry)
        except Exception as e:
            logger.exception(f"Failed to process log entry: {e}")

    async def start(self):
        await self.connect_db()
        await self.connect_nats()
        # Keep the service running
        while True:
            await asyncio.sleep(1)
