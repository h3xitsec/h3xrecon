import asyncpg
import os
from typing import List, Dict, Any
from loguru import logger

DB_CONFIG = {
    'user': os.getenv('H3XRECON_DB_USER'),
    'password': open('/run/secrets/postgresql_db_password','r').read(),
    'database': os.getenv('H3XRECON_DB_NAME'),
    'host': os.getenv('H3XRECON_DB_HOST')
}

class DatabaseManager:
    def __init__(self):
        self.pool = None

    async def ensure_connected(self):
        if self.pool is None:
            await self.connect()

    async def connect(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG)

    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        await self.ensure_connected()
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return []
