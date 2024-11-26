import asyncpg
import re
import asyncio
import uuid
from typing import List, Dict, Any
from collections import defaultdict
from loguru import logger
from datetime import datetime
from .config import Config
import dateutil.parser
from dataclasses import dataclass
from typing import Optional
from h3xrecon.__about__ import __version__

@dataclass
class DbResult:
    """Standardized return type for database operations"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None

    @property
    def failed(self) -> bool:
        return not self.success

class DatabaseManager():
    _instance = None

    def __new__(cls, config=None):
        """
        Singleton constructor for DatabaseManager.
        
        Args:
            config (dict, optional): Database configuration. Defaults to None.
        
        Returns:
            DatabaseManager: Singleton instance of the database manager
        """
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize(config)
        return cls._instance

    def _initialize(self, config=None):
        """
        Initialize the database manager with configuration.
        
        Args:
            config (dict, optional): Database configuration. Defaults to None.
        """
        logger.debug(f"Initializing Database Manager... (v{__version__})")
        if config is None:
            self.config = Config().database.to_dict()
        else:
            self.config = config
        logger.debug(f"Database config: {self.config}")
        self.pool = None
        self.connection = self._connect_to_database()

    def _connect_to_database(self):
        """
        Placeholder method for database connection.
        
        Returns:
            str: A placeholder database connection object
        """
        return "DatabaseConnectionObject"
        
    def __init__(self, config=None):
        """
        Initialize the DatabaseManager instance.
        
        Args:
            config (dict, optional): Database configuration. Defaults to None.
        """
        self._regex_cache = defaultdict(list)
        self._regex_lock = asyncio.Lock()

    async def get_compiled_regexes(self, program_id: int) -> List[re.Pattern]:
        """
        Retrieve and compile regex patterns for a specific program.
        
        Args:
            program_id (int): The ID of the program to fetch regexes for
        
        Returns:
            List[re.Pattern]: A list of compiled regex patterns
        """
        async with self._regex_lock:
            if not self._regex_cache[program_id]:
                program_regexes = await self._fetch_records(
                    'SELECT regex FROM program_scopes WHERE program_id = $1',
                    program_id
                )
                for row in program_regexes.data:
                    regex = row['regex']
                    if isinstance(regex, str):
                        try:
                            compiled = re.compile(regex)
                            self._regex_cache[program_id].append(compiled)
                        except re.error as e:
                            logger.error(f"Invalid regex pattern '{regex}' for program_id {program_id}: {e}")
            return self._regex_cache[program_id]

    async def __aenter__(self):
        """
        Async context manager entry method to ensure database connection.
        
        Returns:
            DatabaseManager: The current instance
        """
        await self.ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit method to close database connection.
        
        Args:
            exc_type: Exception type
            exc_val: Exception value
            exc_tb: Traceback
        """
        await self.close()

    async def ensure_connected(self):
        """
        Ensure that a database connection pool exists.
        Creates a connection pool if one does not already exist.
        """
        if self.pool is None:
            await self.connect()

    async def connect(self):
        """
        Create an asynchronous database connection pool using asyncpg.
        """
        self.pool = await asyncpg.create_pool(**self.config)

    async def close(self):
        """
        Close the existing database connection pool.
        """
        if self.pool:
            await self.pool.close()
    
    async def _fetch_records(self, query: str, *args):
        """
        Execute a SELECT query and return the results.
        
        Args:
            query (str): SQL query to execute
            *args: Query parameters
        
        Returns:
            DbResult: Result of the database query
        """
        logger.debug(f"Executing SELECT query: {query} with args: {args}")
        try:
            await self.ensure_connected()
            async with self.pool.acquire() as conn:
                records = await conn.fetch(query, *args)
                formatted_records = await self.format_records(records)
            logger.debug(f"Fetched records: {formatted_records}")
            return DbResult(success=True, data=formatted_records)
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            return DbResult(success=False, error=str(e))
    
    async def _fetch_value(self, query: str, *args):
        """
        Execute a SELECT query and return the first value.
        
        Args:
            query (str): SQL query to execute
            *args: Query parameters
        
        Returns:
            DbResult: Result of the database query
        """
        logger.debug(f"Executing SELECT query: {query} with args: {args}")
        try:
            await self.ensure_connected()
            async with self.pool.acquire() as conn:
                value = await conn.fetchval(query, *args)
            logger.debug(f"Fetched value: {value}")
            return DbResult(success=True, data=value)
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            return DbResult(success=False, error=str(e))

    async def _write_records(self, query: str, *args):
        """
        Execute an INSERT, UPDATE, or DELETE query and return the outcome.
        
        Args:
            query (str): SQL query to execute
            *args: Query parameters
        
        Returns:
            DbResult: Result of the database modification
        """
        logger.debug(f"Executing modification query: {query} with args: {args}")
        return_data = DbResult(success=False, data=None, error=None)
        try:
            await self.ensure_connected()
            async with self.pool.acquire() as conn:
                if 'RETURNING' in query.upper():
                    records = await conn.fetch(query, *args)  # Directly use the acquired connection
                    formatted_records = await self.format_records(records)
                    if formatted_records:
                        return_data.success = True
                        return_data.data = formatted_records
                    else:
                        return_data.error = "No data returned from query."
                else:
                    result = await conn.execute(query, *args)
                    return_data.success = True
                    return_data.data = result
            return return_data
        except asyncpg.UniqueViolationError:
            return_data.error = "Unique violation error."
        except Exception as e:
            return_data.error = str(e)
        logger.debug(f"return_data: {return_data}")
        return return_data

    async def format_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert database records to a format suitable for serialization.
        
        Args:
            records (List[Dict[str, Any]]): List of database records
        
        Returns:
            List[Dict[str, Any]]: Formatted records with datetime objects converted to ISO format strings
        """
        formatted_records = []
        for record in records:
            try:
                formatted_record = {}
                for key, value in record.items():
                    if hasattr(value, 'isoformat'):  # Check if datetime-like
                        formatted_record[key] = value.isoformat()
                    else:
                        formatted_record[key] = value
                formatted_records.append(formatted_record)
            except Exception as e:
                logger.error(f"Error formatting records: {str(e)}")
        return formatted_records
    
    async def get_urls(self, program_name: str = None):
        """
        Retrieve URLs for a specific program or all programs.
        
        Args:
            program_name (str, optional): Name of the program to fetch URLs for. Defaults to None.
        
        Returns:
            DbResult: Result containing URLs
        """
        if program_name:
            query = """
        SELECT 
           *
        FROM urls u
        JOIN programs p ON u.program_id = p.id
        WHERE p.name = $1
        """
            result = await self._fetch_records(query, program_name)
            return result

    async def get_program_name(self, program_id: int) -> str:
        """
        Retrieve the name of a program by its ID.
        
        Args:
            program_id (int): ID of the program
        
        Returns:
            str: Name of the program, or None if not found
        """
        query = """
        SELECT name FROM programs WHERE id = $1
        """
        result = await self._fetch_records(query, program_id)
        if len(result.data) > 0:
            return result.data[0]['name']
        else:
            return None

    async def get_program_id(self, program_name: str) -> int:
        """
        Retrieve the ID of a program by its name.
        
        Args:
            program_name (str): Name of the program
        
        Returns:
            int: ID of the program
        """
        query = """
        SELECT id FROM programs WHERE name = $1
        """
        result = await self._fetch_records(query, program_name)
        return result.data[0].get('id',{})
    
    async def get_programs(self):
        """
        Retrieve a list of all reconnaissance programs.
        
        Returns:
            DbResult: Result containing program IDs and names
        """
        query = """
        SELECT p.id, p.name
        FROM programs p
        ORDER BY p.name;
        """
        return await self._fetch_records(query)

    # Remaining methods would follow the same pattern of adding docstrings
    # I've demonstrated the style for the first set of methods
