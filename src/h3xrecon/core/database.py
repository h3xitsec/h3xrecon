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
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize(config)
        return cls._instance

    def _initialize(self, config=None):
        # Initialize your database connection here
        logger.debug(f"Initializing Database Manager... (v{__version__})")
        if config is None:
            self.config = Config().database.to_dict()
        else:
            self.config = config
        logger.debug(f"Database config: {self.config}")
        self.pool = None
        self.connection = self._connect_to_database()

    def _connect_to_database(self):
        # Placeholder for actual database connection logic
        return "DatabaseConnectionObject"
        
    def __init__(self, config=None):
        self._regex_cache = defaultdict(list)
        self._regex_lock = asyncio.Lock()

    async def get_compiled_regexes(self, program_id: int) -> List[re.Pattern]:
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
        await self.ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def ensure_connected(self):
        if self.pool is None:
            await self.connect()

    async def connect(self):
        self.pool = await asyncpg.create_pool(**self.config)

    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def _fetch_records(self, query: str, *args):
        """Execute a SELECT query and return the results."""
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
        """Execute a SELECT query and return the first value."""
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
        """Execute an INSERT, UPDATE, or DELETE query and return the outcome."""
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

    async def drop_program_data(self, program_name: str):
        queries = []
        program_id = await self.get_program_id(program_name)
        query = """
        DELETE FROM domains WHERE program_id = $1
        """
        queries.append(query)
        query = """
        DELETE FROM urls WHERE program_id = $1
        """
        queries.append(query)
        query = """
        DELETE FROM services WHERE program_id = $1
        """
        queries.append(query)
        query = """
        DELETE FROM ips WHERE program_id = $1
        """
        queries.append(query)

        for q in queries:
            await self._write_records(q, program_id)


    async def format_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes a list of database records and formats them for further processing
        
        Args:
            records: List of database record dictionaries
            
        Returns:
            List of formatted records with datetime objects converted to ISO format strings
            Empty list if error occurs
        """
            # Convert any datetime objects to strings for JSON serialization
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

    async def get_resolved_domains(self, program_name: str = None):
        query = """
        SELECT 
            d.domain,
            array_agg(i.ip) as resolved_ips
        FROM domains d
        JOIN programs p ON d.program_id = p.id
        JOIN ips i ON i.id = ANY(d.ips)
        WHERE d.ips IS NOT NULL 
        AND array_length(d.ips, 1) > 0
        """
        if program_name:
            query += " AND p.name = $1 GROUP BY d.domain"
            result = await self._fetch_records(query, program_name)
        else:
            query += " GROUP BY d.domain"
            result = await self._fetch_records(query)
        return result

    async def get_unresolved_domains(self, program_name: str = None):
        query = """
        SELECT 
            d.*
        FROM domains d
        JOIN programs p ON d.program_id = p.id
        WHERE (d.ips IS NULL 
        OR array_length(d.ips, 1) = 0 
        OR d.ips = '{}')
        """
        if program_name:
            query += " AND p.name = $1"
            result = await self._fetch_records(query, program_name)
        else:
            result = await self._fetch_records(query)
        return result

    async def get_reverse_resolved_ips(self, program_name: str = None):
        query = """
        SELECT 
            i.*
        FROM ips i
        JOIN programs p ON i.program_id = p.id
        WHERE i.ptr IS NOT NULL
        AND i.ptr != ''
        """
        if program_name:
            query += " AND p.name = $1"
            result = await self._fetch_records(query, program_name)
        else:
            result = await self._fetch_records(query)
        return result

    async def get_not_reverse_resolved_ips(self, program_name: str = None):
        query = """
        SELECT 
            i.*
        FROM ips i
        JOIN programs p ON i.program_id = p.id
        WHERE i.ptr IS NULL
        OR i.ptr = ''
        """
        if program_name:
            query += " AND p.name = $1"
            result = await self._fetch_records(query, program_name)
        else:
            result = await self._fetch_records(query)
        return result

    # async def check_domain_regex_match(self, domain: str, program_id: int) -> bool:
    #     try:
    #         if isinstance(domain, dict) and 'subdomain' in domain:
    #             domain = domain['subdomain']
            
    #         if not isinstance(domain, str):
    #             logger.warning(f"Domain is not a string: {domain}, type: {type(domain)}")
    #             return False

    #         program_regexes = await self._fetch_records(
    #             'SELECT regex FROM program_scopes WHERE program_id = $1',
    #             program_id
    #         )
    #         for row in program_regexes.data:
    #             logger.info(f"Regex: {row['regex']}")
    #             regex = row['regex']
    #             if not isinstance(regex, str):
    #                 logger.warning(f"Regex is not a string: {regex}, type: {type(regex)}")
    #                 continue
    #             try:
    #                 if re.match(regex, domain):
    #                     return True
    #             except re.error as e:
    #                 logger.error(f"Invalid regex pattern: {regex}. Error: {str(e)}")
    #             return False
    #     except Exception as e:
    #         logger.error(f"Error checking domain regex match: {str(e)}")
    #         logger.exception(e)
    #         return False

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
            result = await self._fetch_records(query, program_name)
        else:
            result = await self._fetch(query)
        return result

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
            result = await self._fetch_records(query, program_name)
        else:
            result = await self._fetch_records(query)
        return result

    # Returns the program id if successful, 0 if it already exists
    async def add_program(self, name: str) -> DbResult:
        """Add a new program to the database"""
        query = "INSERT INTO programs (name) VALUES ($1) RETURNING id"
        insert_result = await self._write_records(query, name)
        return insert_result

    async def get_program_name(self, program_id: int) -> str:
        query = """
        SELECT name FROM programs WHERE id = $1
        """
        result = await self._fetch_records(query, program_id)
        if len(result.data) > 0:
            return result.data[0]['name']
        else:
            return None

    async def get_program_id(self, program_name: str) -> int:
        query = """
        SELECT id FROM programs WHERE name = $1
        """
        result = await self._fetch_records(query, program_name)
        return result.data[0].get('id',{})
        # if len(result) > 0:
        #     return result[0]['id']
        # else:
        #     return 0
    
    async def get_program_scope(self, program_name: str) -> List[str]:
        query = """
        SELECT regex FROM program_scopes WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        """
        result = await self._fetch_records(query, program_name)
        return result
    
    async def get_program_cidr(self, program_name: str) -> List[str]:
        query = """
        SELECT cidr FROM program_cidrs WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        """
        result = await self._fetch_records(query, program_name)
        return result

    async def add_program_scope(self, program_name: str, scope: str):
        program_id = await self.get_program_id(program_name)
        if program_id is None:
            raise ValueError(f"Program '{program_name}' not found")
        
        query = """
        INSERT INTO program_scopes (program_id, regex) VALUES ($1, $2)
        """
        return await self._write_records(query, program_id, scope)

    async def add_program_cidr(self, program_name: str, cidr: str):
        program_id = await self.get_program_id(program_name)
        if program_id is None:
            raise ValueError(f"Program '{program_name}' not found")
        
        query = """
        INSERT INTO program_cidrs (program_id, cidr) VALUES ($1, $2)
        """
        return await self._write_records(query, program_id, cidr)


    async def remove_program(self, program_name: str):
        """Remove a program and all its associated data"""
        query = """
        DELETE FROM programs 
        WHERE name = $1
        RETURNING id
        """
        return await self._write_records(query, program_name)

    async def remove_program_scope(self, program_name: str, scope: str):
        """Remove a specific scope regex from a program"""
        query = """
        DELETE FROM program_scopes 
        WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        AND regex = $2
        RETURNING id
        """
        result = await self._write_records(query, program_name, scope)
        if result:
            logger.info(f"Scope removed from program {program_name}: {scope}")
            return True
        return False

    async def remove_program_cidr(self, program_name: str, cidr: str):
        """Remove a specific CIDR from a program"""
        query = """
        DELETE FROM program_cidrs 
        WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        AND cidr = $2
        RETURNING id
        """
        result = await self._write_records(query, program_name, cidr)
        if result:
            logger.info(f"CIDR removed from program {program_name}: {cidr}")
            return True
        return False

    async def get_ips(self, program_name: str = None):
        if program_name:
            query = """
            SELECT 
                *
            FROM ips i
            JOIN programs p ON i.program_id = p.id
            WHERE p.name = $1
            """
            result = await self._fetch_records(query, program_name)
            return result
    
    async def get_programs(self):
        """List all reconnaissance programs"""
        query = """
        SELECT p.id, p.name
        FROM programs p
        ORDER BY p.name;
        """
        return await self._fetch_records(query)
        # Extract the name property from each record and return as a list of strings
        #return await self.formaresult)


    async def insert_service(self, ip: str, program_id: int, port: int = None, protocol: str = None, service: str = None) -> bool:
        try:
            # First get or create the IP record
            ip_record = await self._write_records(
                '''
                INSERT INTO ips (ip, program_id)
                VALUES ($1, $2)
                ON CONFLICT (ip) DO UPDATE 
                SET program_id = EXCLUDED.program_id
                RETURNING id
                ''',
                ip,
                program_id
            )
            
            # Handle nested DbResult for IP record
            if ip_record.success and isinstance(ip_record.data, DbResult):
                ip_data = ip_record.data.data
            else:
                ip_data = ip_record.data

            if not ip_data or not isinstance(ip_data, list) or len(ip_data) == 0:
                raise Exception(f"Failed to insert or get IP record for {ip}")
                
            ip_id = ip_data[0]['id']

            # Use the ON CONFLICT for services with ports
            result = await self._write_records(
                '''
                INSERT INTO services (ip, port, protocol, service, program_id) 
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT ON CONSTRAINT unique_service_ip_port
                DO UPDATE
                SET protocol = EXCLUDED.protocol,
                    service = EXCLUDED.service,
                    program_id = EXCLUDED.program_id,
                    discovered_at = CURRENT_TIMESTAMP
                RETURNING (xmax = 0) AS inserted
                ''',
                ip_id,
                port,
                protocol,
                service,
                program_id
            )
            
            # Handle nested DbResult for service record
            if result.success and isinstance(result.data, DbResult):
                data = result.data.data
            else:
                data = result.data

            if data and isinstance(data, list) and len(data) > 0:
                inserted = data[0]['inserted']
                service_desc = f"{protocol or 'unknown'}:{ip}:{port if port else 'no_port'}"
                if inserted:
                    logger.info(f"New service inserted: {service_desc}")
                else:
                    logger.info(f"Service updated: {service_desc}")
                return inserted
            return False
                
        except Exception as e:
            logger.error(f"Error inserting or updating service in database: {str(e)}")
            logger.exception(e)
            return False
    
    async def insert_domain(self, domain: str, program_id: int, ips: List[str] = None, cnames: List[str] = None, is_catchall: bool = False):
        try:
            logger.debug(f"Checking domain regex match for {domain} in program {program_id}")
            if await self.check_domain_regex_match(domain, program_id):
                # Get IP IDs
                ip_ids = []
                if ips:
                    for ip in ips:
                        ip_id = await self._fetch_value('SELECT id FROM ips WHERE ip = $1', ip)
                        if ip_id:
                            ip_ids.append(ip_id.data)

                result = await self._write_records(
                    '''
                    INSERT INTO domains (domain, program_id, ips, cnames, is_catchall) 
                    VALUES ($1, $2, $3, $4, $5) 
                    ON CONFLICT (domain) DO UPDATE 
                    SET program_id = EXCLUDED.program_id, ips = EXCLUDED.ips, cnames = EXCLUDED.cnames, is_catchall = EXCLUDED.is_catchall
                    RETURNING (xmax = 0) AS inserted
                    ''',
                    domain.lower(),
                    program_id,
                    ip_ids,
                    [c.lower() for c in cnames] if cnames else None,
                    is_catchall
                )
                
                if result.success and isinstance(result.data, DbResult):
                    data = result.data.data
                else:
                    data = result.data

                if data and isinstance(data, list) and len(data) > 0:
                    return data[0]['inserted']
                return False
            else:
                return False
        except Exception as e:
            logger.error(f"Error inserting or updating domain in database: {str(e)}")
            logger.exception(e)
            return False
                        
#    async def insert_url(self, url: str, title: str, chain_status_codes: List[int], status_code: int, final_url: str, program_id: int, scheme: str, port: int, webserver: str, content_type: str, content_length: int, tech: List[str]):
    async def insert_url(self, url: str, httpx_data: Dict[str, Any], program_id: int):
        logger.debug(f"{url}:{httpx_data}")
        await self.ensure_connected()
        try:
            if self.pool is None:
                raise Exception("Database connection pool is not initialized")
            
            # Convert types before insertion
            port = int(httpx_data.get('port')) if httpx_data.get('port') else None
            status_code = int(httpx_data.get('status_code')) if httpx_data.get('status_code') else None
            content_length = int(httpx_data.get('content_length')) if httpx_data.get('content_length') else None
            words = int(httpx_data.get('words')) if httpx_data.get('words') else None
            lines = int(httpx_data.get('lines')) if httpx_data.get('lines') else None
            timestamp = dateutil.parser.parse(httpx_data.get('timestamp')) if httpx_data.get('timestamp') else None
            
            result = await self._write_records(
                '''
                INSERT INTO urls (
                        url, program_id, a, host, path, port, tech, response_time,
                        input, lines, title, words, failed, method, scheme,
                        cdn_name, cdn_type, final_url, resolvers, timestamp,
                        webserver, status_code, content_type, content_length,
                        chain_status_codes
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                        $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
                    )
                    ON CONFLICT (url) DO UPDATE SET
                        a = EXCLUDED.a,
                        host = EXCLUDED.host,
                        path = EXCLUDED.path,
                        port = EXCLUDED.port,
                        tech = EXCLUDED.tech,
                        response_time = EXCLUDED.response_time,
                        input = EXCLUDED.input,
                        lines = EXCLUDED.lines,
                        title = EXCLUDED.title,
                        words = EXCLUDED.words,
                        failed = EXCLUDED.failed,
                        method = EXCLUDED.method,
                        scheme = EXCLUDED.scheme,
                        cdn_name = EXCLUDED.cdn_name,
                        cdn_type = EXCLUDED.cdn_type,
                        final_url = EXCLUDED.final_url,
                        resolvers = EXCLUDED.resolvers,
                        timestamp = EXCLUDED.timestamp,
                        webserver = EXCLUDED.webserver,
                        status_code = EXCLUDED.status_code,
                        content_type = EXCLUDED.content_type,
                        content_length = EXCLUDED.content_length,
                        chain_status_codes = EXCLUDED.chain_status_codes
                    RETURNING (xmax = 0) AS inserted
                ''',
                url.lower(),
                program_id,
                httpx_data.get('a'),
                httpx_data.get('host'),
                httpx_data.get('path'),
                port,
                httpx_data.get('tech'),
                httpx_data.get('time'),  # response_time
                httpx_data.get('input'),
                lines,
                httpx_data.get('title'),
                words,
                httpx_data.get('failed', False),
                httpx_data.get('method'),
                httpx_data.get('scheme'),
                httpx_data.get('cdn_name'),
                httpx_data.get('cdn_type'),
                httpx_data.get('final_url'),
                httpx_data.get('resolvers'),
                timestamp,
                httpx_data.get('webserver'),
                status_code,
                httpx_data.get('content_type'),
                content_length,
                httpx_data.get('chain_status_codes')
            )
            
            # Handle nested DbResult objects
            if result.success and isinstance(result.data, DbResult):
                data = result.data.data
            else:
                data = result.data

            if data and isinstance(data, list) and len(data) > 0:
                inserted = data[0]['inserted']
                if inserted:
                    logger.info(f"New URL inserted: {url}")
                else:
                    logger.info(f"URL updated: {url}")
                return inserted
            return False
        except Exception as e:
            logger.error(f"Error inserting or updating URL in database: {e}")
            logger.exception(e)
            return False
    
    async def check_domain_regex_match(self, domain: str, program_id: int) -> bool:
        try:
            if isinstance(domain, dict) and 'subdomain' in domain:
                domain = domain['subdomain']
            
            if not isinstance(domain, str):
                logger.warning(f"Domain is not a string: {domain}, type: {type(domain)}")
                return False
            
            compiled_regexes = await self.get_compiled_regexes(program_id)
            for regex in compiled_regexes:
                if regex.match(domain):
                    return True
            await self.insert_out_of_scope_domain(domain, program_id)
            logger.debug(f"Domain {domain} inserted as out-of-scope for program {program_id}")
            return False
        except Exception as e:
            logger.error(f"Error checking domain regex match: {str(e)}")
            logger.exception(e)
            return False
        finally:
            logger.debug("Exiting check_domain_regex_match method")

    async def insert_ip(self, ip: str, ptr: str, program_id: int) -> bool:
        query = """
        INSERT INTO ips (ip, ptr, program_id)
        VALUES ($1, LOWER($2), $3)
        ON CONFLICT (ip) DO UPDATE
        SET ptr = CASE
                WHEN EXCLUDED.ptr IS NOT NULL AND EXCLUDED.ptr <> '' THEN EXCLUDED.ptr
                ELSE ips.ptr
            END,
            program_id = EXCLUDED.program_id,
            discovered_at = CURRENT_TIMESTAMP
        RETURNING id, (xmax = 0) AS inserted
        """
        try:
            result = await self._write_records(query, ip, ptr, program_id)
            
            # Handle nested DbResult objects
            if result.success and isinstance(result.data, DbResult):
                data = result.data.data
            else:
                data = result.data

            if data and isinstance(data, list) and len(data) > 0:
                inserted = data[0]['inserted']
                if inserted:
                    logger.info(f"New IP inserted: {ip}")
                else:
                    logger.info(f"IP updated: {ip}")
                return inserted
            return False
        except Exception as e:
            logger.error(f"Error inserting IP: {e}")
            return False

    async def log_or_update_function_execution(self, log_entry: Dict[str, Any]):
        await self.ensure_connected()
        try:
            # Check if the execution already exists
            existing = await self._fetch_records('''
                SELECT * FROM function_logs 
                WHERE execution_id = $1
            ''', uuid.UUID(log_entry['execution_id']))

            if existing:
                # Update existing log entry
                await self._write_records('''
                    UPDATE function_logs 
                    SET timestamp = $1
                    WHERE execution_id = $2
                ''',
                    datetime.fromisoformat(log_entry['timestamp']),
                    uuid.UUID(log_entry['execution_id'])
                )
                #logger.debug(f"Updated log entry: {log_entry['execution_id']}")
            else:
                # Insert new log entry
                await self._write_records('''
                    INSERT INTO function_logs 
                    (execution_id, timestamp, function_name, target, program_id) 
                    VALUES ($1, $2, $3, $4, $5)
                ''',
                    uuid.UUID(log_entry['execution_id']),
                    datetime.fromisoformat(log_entry['timestamp']),
                    log_entry['function_name'],
                    log_entry['target'],
                    log_entry['program_id']
                )
                #logger.debug(f"Inserted new log entry: {log_entry['execution_id']}")
        except Exception as e:
            logger.error(f"Error logging or updating function execution in database: {e}")
            logger.exception(e)
    
    async def insert_out_of_scope_domain(self, domain: str, program_id: int):
        try:
            await self._write_records('''
                INSERT INTO out_of_scope_domains (domain, program_ids)
                VALUES ($1, ARRAY[$2]::integer[])
                ON CONFLICT (domain) 
                DO UPDATE SET program_ids = 
                    CASE 
                        WHEN $2 = ANY(out_of_scope_domains.program_ids) THEN out_of_scope_domains.program_ids
                        ELSE array_append(out_of_scope_domains.program_ids, $2)
                    END
            ''', domain.lower(), program_id)
            logger.info(f"Out-of-scope domain inserted/updated: {domain} for program {program_id}")
        except Exception as e:
            logger.error(f"Error inserting/updating out-of-scope domain in database: {str(e)}")
            logger.exception(e)

    async def remove_domain(self, program_name: str, domain: str):
        """Remove a specific domain from a program"""
        query = """
        DELETE FROM domains 
        WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        AND domain = $2
        RETURNING id
        """
        result = await self._fetch_value(query, program_name, domain)
        if result:
            logger.info(f"Domain removed from program {program_name}: {domain}")
            return True
        return False

    async def remove_ip(self, program_name: str, ip: str):
        """Remove a specific IP from a program"""
        query = """
        DELETE FROM ips 
        WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        AND ip = $2
        RETURNING id
        """
        result = await self._fetch_value(query, program_name, ip)
        if result:
            logger.info(f"IP removed from program {program_name}: {ip}")
            return True
        return False

    async def remove_url(self, program_name: str, url: str):
        """Remove a specific URL from a program"""
        query = """
        DELETE FROM urls 
        WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        AND url = $2
        RETURNING id
        """
        result = await self._fetch_value(query, program_name, url)
        if result:
            logger.info(f"URL removed from program {program_name}: {url}")
            return True
        return False
