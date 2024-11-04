import asyncpg
import os
from typing import List, Dict, Any
from loguru import logger

DB_CONFIG = {
    'user': os.getenv('H3XRECON_DB_USER'),
    'password': os.getenv('H3XRECON_DB_USER'),
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
    
    async def list_domains(self, program_name: str = None):
        if program_name:
            query = """
            SELECT 
                d.domain,
                p.name as program_name
            FROM domains d
            JOIN programs p ON d.program_id = p.id
            WHERE p.name = $1
            """
            result = await self.execute_query(query, program_name)
            return [record['domain'] for record in result]
    
    async def list_ips(self, program_name: str = None):
        if program_name:
            query = """
            SELECT 
                i.ip,
                p.name as program_name
            FROM ips i
            JOIN programs p ON i.program_id = p.id
            WHERE p.name = $1
            """
            result = await self.execute_query(query, program_name)
            return [record['ip'] for record in result]

    async def list_urls(self, program_name: str = None):
        if program_name:
            query = """
            SELECT 
                u.url,
                p.name as program_name
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE p.name = $1
            """
            result = await self.execute_query(query, program_name)
            return [record['url'] for record in result]
    
    async def list_programs(self):
        """List all reconnaissance programs"""
        query = """
        SELECT p.name
        FROM programs p
        ORDER BY p.name;
        """
        result = await self.execute_query(query)
        # Extract the name property from each record and return as a list of strings
        return [record['name'] for record in result]

    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        await self.ensure_connected()
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return []
