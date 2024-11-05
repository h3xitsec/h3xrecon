import asyncpg
import os
import json
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
    

    async def format_json_output(self, records: List[Dict[str, Any]]) -> str:
        """
        Takes a list of database records and formats them as a JSON string
        
        Args:
            records: List of database record dictionaries
            
        Returns:
            Formatted JSON string representation of the records
        """
        try:
            # Convert any datetime objects to strings for JSON serialization
            formatted_records = []
            for record in records:
                formatted_record = {}
                for key, value in record.items():
                    if hasattr(value, 'isoformat'):  # Check if datetime-like
                        formatted_record[key] = value.isoformat()
                    else:
                        formatted_record[key] = value
                formatted_records.append(formatted_record)
                
            return formatted_records
            
        except Exception as e:
            logger.error(f"Error formatting JSON output: {str(e)}")
            return json.dumps({"error": "Failed to format records"})

    async def get_domains(self, program_name: str = None):
        query = """
        SELECT 
            *
        FROM domains d
        JOIN programs p ON d.program_id = p.id
        """
        if program_name:
            query += """
            WHERE p.name = $1
            """
            result = await self.execute_query(query, program_name)
        else:
            result = await self.execute_query(query)
        return await self.format_json_output(result)

    async def get_services(self, program_name: str = None):
        query = """
        SELECT 
            *,
            p.name as program_name
        FROM services s
        JOIN ips i ON s.ip = i.id
        JOIN programs p ON s.program_id = p.id
        """
        if program_name:
            query += """
            WHERE p.name = $1
            """
            result = await self.execute_query(query, program_name)
        else:
            result = await self.execute_query(query)
        return await self.format_json_output(result)

    async def add_program(self, program_name: str, scope: List = None, cidr: List = None):
        query = """
        INSERT INTO programs (name) VALUES ($1) RETURNING id
        """
        result = await self.execute_query(query, program_name)
        program_id = result[0]['id']
        if scope:
            await self.add_program_scope(program_name, scope)
        if cidr:
            await self.add_program_cidr(program_name, cidr)

    async def get_program_id(self, program_name: str) -> int:
        query = """
        SELECT id FROM programs WHERE name = $1
        """
        result = await self.execute_query(query, program_name)
        return result[0]['id']
    
    async def get_program_scope(self, program_name: str) -> List[str]:
        query = """
        SELECT regex FROM program_scopes WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        """
        result = await self.execute_query(query, program_name)
        return [r['regex'] for r in result]
    
    async def get_program_cidr(self, program_name: str) -> List[str]:
        query = """
        SELECT cidr FROM program_cidrs WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        """
        result = await self.execute_query(query, program_name)
        return [r['cidr'] for r in result]

    async def add_program_scope(self, program_name: str, scope: str):
        program_id = await self.get_program_id(program_name)
        if program_id is None:
            raise ValueError(f"Program '{program_name}' not found")
        
        query = """
        INSERT INTO program_scopes (program_id, regex) VALUES ($1, $2)
        """
        await self.execute_query(query, program_id, scope)
    
    async def add_program_cidr(self, program_name: str, cidr: str):
        program_id = await self.get_program_id(program_name)
        if program_id is None:
            raise ValueError(f"Program '{program_name}' not found")
        
        query = """
        INSERT INTO program_cidrs (program_id, cidr) VALUES ($1, $2)
        """
        await self.execute_query(query, program_id, cidr)

    async def get_ips(self, program_name: str = None):
        if program_name:
            query = """
            SELECT 
                *
            FROM ips i
            JOIN programs p ON i.program_id = p.id
            WHERE p.name = $1
            """
            result = await self.execute_query(query, program_name)
            return await self.format_json_output(result)

    async def get_urls(self, program_name: str = None):
        if program_name:
            query = """
            SELECT 
                *
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE p.name = $1
            """
            result = await self.execute_query(query, program_name)
            return await self.format_json_output(result)
    
    async def get_programs(self):
        """List all reconnaissance programs"""
        query = """
        SELECT p.name
        FROM programs p
        ORDER BY p.name;
        """
        result = await self.execute_query(query)
        # Extract the name property from each record and return as a list of strings
        return await self.format_json_output(result)

    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        logger.debug(f"Executing query: {query} with args: {args}")
        await self.ensure_connected()
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return []
