import asyncpg
import re
import asyncio
from typing import List, Dict, Any
from collections import defaultdict
from loguru import logger
from datetime import datetime
from .config import Config
import dateutil.parser
from dataclasses import dataclass
from typing import Optional
from h3xrecon.__about__ import __version__
from h3xrecon.core.utils import parse_url
import json

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
            scope_count = await self._fetch_value('SELECT COUNT(*) FROM program_scopes_domains WHERE program_id = $1', program_id)
            if not self._regex_cache[program_id] or len(self._regex_cache[program_id]) < scope_count.data:
                logger.debug(f"Regex cache for program_id {program_id} is empty or has fewer regexes than scope count. Refreshing...")
                program_regexes = await self._fetch_records(
                    'SELECT regex FROM program_scopes_domains WHERE program_id = $1',
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
            else:
                logger.debug(f"Regex cache for program_id {program_id} already exists: {len(self._regex_cache[program_id])} scopes")
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
        logger.debug("Starting _fetch_records...")
        try:
            logger.debug("Ensuring connection...")
            await self.ensure_connected()
            
            logger.debug("Acquiring connection from pool...")
            try:
                async with asyncio.timeout(10):
                    async with self.pool.acquire() as conn:
                        logger.debug(f"Preparing to execute query: {query[:100]}...")  # Log first 100 chars of query
                        logger.debug(f"Query parameters: {args}")
                        
                        try:
                            records = await asyncio.wait_for(
                                conn.fetch(query, *args),
                                timeout=30
                            )
                            logger.debug(f"Query complete, got {len(records)} records")
                            
                            formatted_records = await self.format_records(records)
                            logger.debug("Records formatted successfully")
                            
                            return DbResult(success=True, data=formatted_records)
                            
                        except asyncio.TimeoutError:
                            logger.error("Query execution timed out after 30 seconds")
                            return DbResult(success=False, error="Query execution timed out")
                        except Exception as e:
                            logger.error(f"Error during query execution: {str(e)}", exc_info=True)
                            return DbResult(success=False, error=str(e))
            
            except asyncio.TimeoutError:
                logger.error("Connection pool acquisition timed out after 10 seconds")
                return DbResult(success=False, error="Connection pool acquisition timed out")
            except Exception as e:
                logger.error(f"Error acquiring connection: {str(e)}", exc_info=True)
                return DbResult(success=False, error=str(e))
            
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}", exc_info=True)
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
        logger.debug(f"Executing SELECT query: {query.replace(chr(10), ' ')} with args: {args}")
        try:
            await self.ensure_connected()
            async with self.pool.acquire() as conn:
                value = await conn.fetchval(query, *args)
            #logger.debug(f"Fetched value: {value}")
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
        logger.debug(f"Executing modification query: {query.replace(chr(10), ' ')} with args: {args}")
        return_data = DbResult(success=False, data=None, error=None)
        try:
            await self.ensure_connected()
            async with self.pool.acquire() as conn:
                async with conn.transaction():  # Explicit transaction
                    if 'RETURNING' in query.upper():
                        records = await conn.fetch(query, *args)
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
        logger.debug(f"Result: {result}")
        if len(result.data) > 0:
            logger.debug(result.data[0]['name'])
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

    async def insert_dns_record(self, domain_id: int, program_id: int, hostname: str, ttl: int, dns_class: str, dns_type: str, value: str):
        try:
            # Validate that value is not null or empty
            if not value or value.strip() == '""' or value.strip() == "''":
                logger.warning(f"RECORD SKIPPED [DNS]: {hostname} {dns_type} - Empty or null value")
                return DbResult(success=False, error="DNS record value cannot be null or empty")

            # First check if record exists and get current values
            existing = await self._fetch_records(
                '''
                SELECT id, ttl, dns_class
                FROM dns_records 
                WHERE domain_id = $1 AND hostname = $2 AND dns_type = $3 AND value = $4
                ''',
                domain_id, hostname.lower(), dns_type, value
            )
            
            if existing.success and existing.data:
                current = existing.data[0]
                # Check if any values would actually change
                needs_update = False
                update_fields = []
                
                if ttl is not None and current['ttl'] != ttl:
                    needs_update = True
                    update_fields.append(f"ttl: {current['ttl']} -> {ttl}")
                
                if dns_class is not None and current['dns_class'] != dns_class:
                    needs_update = True
                    update_fields.append(f"dns_class: {current['dns_class']} -> {dns_class}")
                
                if not needs_update:
                    details = f"{hostname} {dns_type} {value}"
                    logger.debug(f"RECORD UNCHANGED [DNS]: {details}")
                    return DbResult(success=True, data={'id': current['id'], 'inserted': None})

            result = await self._write_records(
                '''
                WITH dns_update AS (
                    INSERT INTO dns_records (domain_id, program_id, hostname, ttl, dns_class, dns_type, value)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (domain_id, hostname, dns_type, value) 
                    DO UPDATE SET
                        ttl = $4,
                        dns_class = $5,
                        program_id = $2
                    WHERE 
                        dns_records.ttl IS DISTINCT FROM $4 OR
                        dns_records.dns_class IS DISTINCT FROM $5
                    RETURNING id, 
                        (xmax = 0) as is_insert,
                        CASE 
                            WHEN xmax = 0 THEN true
                            WHEN xmax <> 0 AND (dns_records.ttl IS DISTINCT FROM $4 OR dns_records.dns_class IS DISTINCT FROM $5) THEN false
                            ELSE null
                        END as modified
                )
                SELECT * FROM dns_update
                ''',
                domain_id,
                program_id,
                hostname.lower(),
                ttl,
                dns_class,
                dns_type,
                value
            )
            
            if result.success and isinstance(result.data, list) and len(result.data) > 0:
                details = f"{hostname} {dns_type} {value}"
                logger.debug(f"Operation result for DNS record {details}: {result.data[0]}")
                
                if result.data[0].get('is_insert', False):
                    logger.success(f"RECORD INSERTED [DNS]: {details}")
                    return DbResult(success=True, data={'id': result.data[0]['id'], 'inserted': True})
                elif result.data[0].get('modified', False):
                    logger.info(f"RECORD UPDATED [DNS]: {details} - Changes: {', '.join(update_fields)}")
                    return DbResult(success=True, data={'id': result.data[0]['id'], 'inserted': False})
                else:
                    logger.debug(f"RECORD UNCHANGED [DNS]: {details}")
                    return DbResult(success=True, data={'id': result.data[0]['id'], 'inserted': None})
            else:
                logger.error(f"Failed to insert or update DNS record in database: {result.error}")
                return DbResult(success=False, error=f"Error inserting or updating DNS record in database: {result.error}")
        except Exception as e:
            logger.error(f"Error inserting DNS record: {str(e)}")
            logger.exception(e)
            return DbResult(success=False, error=f"Error inserting DNS record in database: {str(e)}")

    async def insert_out_of_scope_domain(self, domain: str, program_id: int):
        try:
            # Validate domain before insertion
            if not self.is_valid_domain(domain):
                logger.warning(f"Invalid domain format: {domain}")
                return

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

    def is_valid_domain(self, domain: str) -> bool:
        """
        Validate domain name format
        
        Args:
            domain (str): Domain to validate
        
        Returns:
            bool: True if domain is valid, False otherwise
        """
        # Regex to validate domain names
        # Excludes wildcards, email addresses, and invalid characters
        domain_regex = re.compile(
            r'^(?!-)'                  # Cannot start with a hyphen
            r'(?:[a-zA-Z0-9-]{1,63}\.)*'  # Optional subdomains
            r'[a-zA-Z0-9-]{1,63}'      # Domain name
            r'\.[a-zA-Z]{2,}$'         # Top-level domain
        )
        
        # Remove any whitespace and convert to lowercase
        domain = domain.strip().lower()
        
        # Check against regex and additional conditions
        return (
            domain_regex.match(domain) is not None and
            not domain.startswith('*.') and  # No wildcards
            '@' not in domain  # No email addresses
        )
    async def get_cloud_provider(self, ip: str) -> str:
        try:
            query = """
            SELECT cloud_provider FROM ips WHERE ip = $1
            """
            result = await self._fetch_value(query, ip)
            if result.data:
                return result.data
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting cloud provider: {str(e)}")
            logger.exception(e)
            return None
    
    async def check_domain_regex_match(self, domain: str, program_id: int) -> bool:
        try:
            if isinstance(domain, dict) and 'subdomain' in domain:
                domain = domain['subdomain']
            
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


    async def insert_screenshot(self, program_id: int, url: str, filepath: str, md5_hash: str) -> bool:
        try:
            parsed_url = parse_url(url)
            if parsed_url.get('website', None) is None:
                logger.error(f"Website not found for URL: {url}")
                raise Exception(f"Website not found for URL: {url}")
            website_id = await self._fetch_value('''
                SELECT id FROM websites WHERE url = $1
            ''', parsed_url.get('website').get('url')) 
            logger.debug(f"Website ID: {website_id}")
            result = await self._write_records(
                '''INSERT INTO screenshots (program_id, filepath, md5_hash, website_id) VALUES ($1, $2, $3, $4) 
                ON CONFLICT (program_id, filepath) DO UPDATE 
                SET md5_hash = CASE 
                    WHEN EXCLUDED.md5_hash IS NOT NULL AND EXCLUDED.md5_hash <> screenshots.md5_hash THEN EXCLUDED.md5_hash 
                    ELSE screenshots.md5_hash 
                END,
                updated_at = CASE 
                    WHEN EXCLUDED.md5_hash IS NOT NULL AND EXCLUDED.md5_hash <> screenshots.md5_hash THEN CURRENT_TIMESTAMP 
                    ELSE screenshots.updated_at 
                END,
                website_id = CASE 
                    WHEN EXCLUDED.website_id IS NOT NULL THEN EXCLUDED.website_id 
                    ELSE screenshots.website_id 
                END
                RETURNING (xmax = 0) AS inserted, id''',
                program_id, filepath, md5_hash, website_id.data
            )
            logger.debug(f"Insert result: {result}")
            if result.success and isinstance(result.data, list) and len(result.data) > 0:
                if result.data[0]['inserted']:
                    logger.success(f"INSERTED SCREENSHOT: {filepath}")
                else:
                    logger.info(f"UPDATED SCREENSHOT: {filepath}")
                return {
                    'inserted': result.data[0]['inserted'],
                    'id': result.data[0]['id']
                }
            return {'inserted': False, 'id': None}
        except Exception as e:
            logger.error(f"Error inserting screenshot: {str(e)}")
            return False

    async def insert_ip(self, ip: str, ptr: str, cloud_provider: str, program_id: int) -> Dict[str, Any]:
        try:
            # Validate IP address is IPv4 or IPv6
            import ipaddress
            try:
                ip_obj = ipaddress.ip_address(ip)
                if not isinstance(ip_obj, ipaddress.IPv4Address):
                    return DbResult(success=False, error=f"IPv6 addresses are not supported: {ip}")
            except ValueError as e:
                return DbResult(success=False, error=f"Invalid IP address: {ip}")

            result = await self._write_records(
                '''
                WITH updated_ip AS (
                    INSERT INTO ips (ip, ptr, cloud_provider, program_id)
                    VALUES ($1, LOWER($2), $3, $4)
                    ON CONFLICT (ip) DO UPDATE
                    SET ptr = CASE
                            WHEN EXCLUDED.ptr IS NOT NULL AND EXCLUDED.ptr <> '' AND EXCLUDED.ptr IS DISTINCT FROM ips.ptr THEN EXCLUDED.ptr
                            ELSE ips.ptr
                        END,
                        cloud_provider = CASE
                            WHEN EXCLUDED.cloud_provider IS NOT NULL AND EXCLUDED.cloud_provider <> '' AND EXCLUDED.cloud_provider IS DISTINCT FROM ips.cloud_provider THEN EXCLUDED.cloud_provider
                            ELSE ips.cloud_provider
                        END,
                        program_id = CASE
                            WHEN EXCLUDED.program_id IS NOT NULL AND EXCLUDED.program_id IS DISTINCT FROM ips.program_id THEN EXCLUDED.program_id
                            ELSE ips.program_id
                        END,
                        discovered_at = CASE
                            WHEN (EXCLUDED.ptr IS NOT NULL AND EXCLUDED.ptr <> '' AND EXCLUDED.ptr IS DISTINCT FROM ips.ptr) OR
                                 (EXCLUDED.cloud_provider IS NOT NULL AND EXCLUDED.cloud_provider <> '' AND EXCLUDED.cloud_provider IS DISTINCT FROM ips.cloud_provider) OR
                                 (EXCLUDED.program_id IS NOT NULL AND EXCLUDED.program_id IS DISTINCT FROM ips.program_id)
                            THEN CURRENT_TIMESTAMP
                            ELSE ips.discovered_at
                        END
                    WHERE
                        (EXCLUDED.ptr IS NOT NULL AND EXCLUDED.ptr <> '' AND EXCLUDED.ptr IS DISTINCT FROM ips.ptr) OR
                        (EXCLUDED.cloud_provider IS NOT NULL AND EXCLUDED.cloud_provider <> '' AND EXCLUDED.cloud_provider IS DISTINCT FROM ips.cloud_provider) OR
                        (EXCLUDED.program_id IS NOT NULL AND EXCLUDED.program_id IS DISTINCT FROM ips.program_id)
                    RETURNING *, xmax, (xmax = 0) as is_insert
                ), existing_ip AS (
                    SELECT id, ptr, cloud_provider, program_id, discovered_at
                    FROM ips 
                    WHERE ip = $1 
                    AND NOT EXISTS (SELECT 1 FROM updated_ip)
                )
                SELECT 
                    COALESCE(ui.id, ei.id) as id,
                    CASE 
                        WHEN ui.is_insert THEN true
                        WHEN ui.xmax IS NOT NULL THEN false
                        ELSE null
                    END as inserted
                FROM updated_ip ui
                FULL OUTER JOIN existing_ip ei ON true
                WHERE ui.id IS NOT NULL OR ei.id IS NOT NULL
                LIMIT 1
                ''',
                ip,
                ptr,
                cloud_provider,
                program_id
            )
            
            if result.success and isinstance(result.data, list) and len(result.data) > 0:
                record = result.data[0]
                details = f"{ip}{f' PTR:{ptr}' if ptr else ''}{f' Cloud:{cloud_provider}' if cloud_provider else ''}"
                logger.debug(f"Operation result for IP {ip}: {record}")
                
                inserted = record.get('inserted')
                if inserted is True:
                    logger.success(f"RECORD INSERTED [IP]: {details}")
                elif inserted is False:
                    logger.info(f"RECORD UPDATED [IP]: {details}")
                elif inserted is None:
                    logger.debug(f"RECORD UNCHANGED [IP]: {details}")
                else:
                    logger.warning(f"UNEXPECTED STATUS FOR IP: {details} - Status: {inserted}")
                
                return DbResult(success=True, data={
                    'id': record.get('id'),
                    'inserted': inserted
                })
            else:
                logger.error(f"Failed to insert or update IP in database: {result.error}")
                return DbResult(success=False, error=f"Error inserting or updating IP in database: {result.error}")
        except Exception as e:
            logger.error(f"Error inserting or updating IP in database: {str(e)}")
            logger.exception(e)
            return DbResult(success=False, error=f"Error inserting or updating IP in database: {str(e)}")
    
    async def insert_service(self, ip: str, program_id: int, port: int = None, protocol: str = None, service: str = None) -> bool:
        try:
            # First get or create the IP record
            ip_record = await self.insert_ip(ip, None, None, program_id)
            
            if not ip_record.success:
                logger.warning(ip_record.error)
                return DbResult(success=False, error=ip_record.error)
                
            # Access the 'id' from the data dictionary inside the DbResult object
            ip_id = ip_record.data.get('id')
            if not ip_id:
                return DbResult(success=False, error=f"No ID returned for IP record {ip}")

            # Use the ON CONFLICT for services with ports
            result = await self._write_records(
                '''
                WITH service_update AS (
                    INSERT INTO services (ip, port, protocol, service, program_id) 
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT ON CONSTRAINT unique_service_ip_port
                    DO UPDATE
                    SET protocol = CASE
                            WHEN $3 IS NOT NULL AND $3 IS DISTINCT FROM services.protocol THEN $3
                            ELSE services.protocol
                        END,
                        service = CASE
                            WHEN $4 IS NOT NULL AND $4 IS DISTINCT FROM services.service THEN $4
                            ELSE services.service
                        END,
                        program_id = CASE
                            WHEN $5 IS NOT NULL AND $5 IS DISTINCT FROM services.program_id THEN $5
                            ELSE services.program_id
                        END,
                        discovered_at = CASE
                            WHEN ($3 IS NOT NULL AND $3 IS DISTINCT FROM services.protocol) OR
                                 ($4 IS NOT NULL AND $4 IS DISTINCT FROM services.service) OR
                                 ($5 IS NOT NULL AND $5 IS DISTINCT FROM services.program_id)
                            THEN CURRENT_TIMESTAMP
                            ELSE services.discovered_at
                        END
                    WHERE
                        ($3 IS NOT NULL AND $3 IS DISTINCT FROM services.protocol) OR
                        ($4 IS NOT NULL AND $4 IS DISTINCT FROM services.service) OR
                        ($5 IS NOT NULL AND $5 IS DISTINCT FROM services.program_id)
                    RETURNING *, (xmax = 0) as is_insert
                )
                SELECT * FROM service_update
                ''',
                ip_id,
                port,
                protocol,
                service,
                program_id
            )
            
            if result.success and isinstance(result.data, list) and len(result.data) > 0:
                details = f"{ip} Port:{port} Protocol:{protocol} Service:{service}"
                logger.debug(f"Operation result for service {details}: {result.data[0]}")
                if result.data[0].get('is_insert', False):
                    logger.success(f"RECORD INSERTED [SERVICE]: {details}")
                elif result.data[0].get('modified', False):
                    logger.info(f"RECORD UPDATED [SERVICE]: {details}")
                else:
                    logger.debug(f"RECORD UNCHANGED [SERVICE]: {details}")
                return DbResult(success=True, data=result.data[0])
            else:
                return DbResult(success=False, error=f"Error inserting or updating service in database: {result.error}")
                
        except Exception as e:
            logger.error(f"Error inserting or updating service in database: {str(e)}")
            logger.exception(e)
            return DbResult(success=False, error=f"Error inserting or updating service in database: {str(e)}")
    
    async def insert_domain(self, domain: str, program_id: int, ips: List[str] = None, cnames: List[str] = None, is_catchall: bool = None) -> Dict[str, Any]:
        try:
            logger.debug(f"insert_domain called with is_catchall={is_catchall}, type={type(is_catchall)}")
            if await self.check_domain_regex_match(domain, program_id):
                # Get IP IDs
                ip_ids = []
                if ips:
                    for ip in ips:
                        ip_id = await self._fetch_value('SELECT id FROM ips WHERE ip = $1', ip)
                        if ip_id and ip_id.data is not None:
                            ip_ids.append(ip_id.data)
                    logger.debug(f"IP IDs for domain {domain}: {ip_ids}")

                result = await self._write_records(
                    '''
                    WITH updated_domain AS (
                        INSERT INTO domains (domain, program_id, ips, cnames, is_catchall) 
                        VALUES ($1, $2, $3, $4, $5::boolean) 
                        ON CONFLICT (domain) DO UPDATE 
                        SET program_id = CASE
                                WHEN EXCLUDED.program_id IS NOT NULL AND EXCLUDED.program_id IS DISTINCT FROM domains.program_id THEN EXCLUDED.program_id
                                ELSE domains.program_id
                            END,
                            ips = CASE
                                WHEN EXCLUDED.ips IS NOT NULL AND EXCLUDED.ips IS DISTINCT FROM domains.ips THEN 
                                    CASE
                                        WHEN domains.ips IS NULL THEN EXCLUDED.ips
                                        ELSE (
                                            SELECT ARRAY(
                                                SELECT DISTINCT elem
                                                FROM UNNEST(domains.ips || EXCLUDED.ips) AS elem
                                                WHERE elem IS NOT NULL
                                            )
                                        )
                                    END
                                ELSE domains.ips
                            END,
                            cnames = CASE
                                WHEN EXCLUDED.cnames IS NOT NULL AND EXCLUDED.cnames IS DISTINCT FROM domains.cnames THEN EXCLUDED.cnames
                                ELSE domains.cnames
                            END,
                            is_catchall = CASE
                                WHEN EXCLUDED.is_catchall IS NOT NULL AND EXCLUDED.is_catchall IS DISTINCT FROM domains.is_catchall THEN EXCLUDED.is_catchall::boolean
                                ELSE domains.is_catchall
                            END
                        WHERE
                            (EXCLUDED.program_id IS NOT NULL AND EXCLUDED.program_id IS DISTINCT FROM domains.program_id) OR
                            (EXCLUDED.ips IS NOT NULL AND EXCLUDED.ips IS DISTINCT FROM domains.ips) OR
                            (EXCLUDED.cnames IS NOT NULL AND EXCLUDED.cnames IS DISTINCT FROM domains.cnames) OR
                            (EXCLUDED.is_catchall IS NOT NULL AND EXCLUDED.is_catchall IS DISTINCT FROM domains.is_catchall)
                        RETURNING *, xmax, (xmax = 0) as is_insert
                    ), existing_domain AS (
                        SELECT id, is_catchall
                        FROM domains 
                        WHERE domain = $1 
                        AND NOT EXISTS (SELECT 1 FROM updated_domain)
                    )
                    SELECT 
                        COALESCE(ud.id, ed.id) as id,
                        COALESCE(ud.is_catchall, ed.is_catchall) as is_catchall,
                        CASE 
                            WHEN ud.is_insert THEN true
                            WHEN ud.xmax IS NOT NULL THEN false
                            ELSE null
                        END as inserted
                    FROM updated_domain ud
                    FULL OUTER JOIN existing_domain ed ON true
                    WHERE ud.id IS NOT NULL OR ed.id IS NOT NULL
                    LIMIT 1
                    ''',
                    domain.lower(),
                    program_id,
                    ip_ids if ip_ids else None,
                    [c.lower() for c in cnames] if cnames else None,
                    is_catchall
                )
                logger.debug(f"Insert result: {result}")
                
                if result.success and isinstance(result.data, list) and len(result.data) > 0:
                    details = f"{domain}{f' IPs:{ips}' if ips else ''}{f' Cnames:{cnames}' if cnames else ''}{f' Wildcard:{is_catchall}' if is_catchall else ''}"
                    logger.debug(f"Operation result for domain {domain}: {result.data[0]}")
                    if result.data[0]['inserted'] is True:
                        logger.success(f"RECORD INSERTED [DOMAIN]: {details}")
                    elif result.data[0]['inserted'] is False:
                        logger.info(f"RECORD UPDATED [DOMAIN]: {details}")
                    elif result.data[0]['inserted'] is None:
                        logger.debug(f"RECORD UNCHANGED [DOMAIN]: {details}")
                    else:
                        logger.warning(f"UNEXPECTED STATUS FOR DOMAIN: {details} - Status: {result.data[0]['inserted']}")
                    return DbResult(success=True, data={
                        'inserted': result.data[0]['inserted'],
                        'id': result.data[0]['id'],
                        'is_catchall': result.data[0]['is_catchall']
                    })
                else:
                    logger.error(f"Failed to insert or update domain in database: {result.error}")
                    return DbResult(success=False, error=f"Error inserting or updating domain in database: {result.error}")
        except Exception as e:
            logger.error(f"Error inserting or updating domain in database: {str(e)}")
            logger.exception(e)
            return DbResult(success=False, error=f"Error inserting or updating domain in database: {str(e)}")
        
    async def insert_website(self, url: str, host: str = None, port: int = None, scheme: str = None, techs: List[str] = None, favicon_hash: str = None, favicon_url: str = None, program_id: int = None):
        await self.ensure_connected()
        try:
            # Validate URL
            import re
            url_pattern = re.compile(
                r'^https?://'  # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            
            if not url_pattern.match(url):
                logger.error(f"Invalid URL format: {url}")
                return False

            if self.pool is None:
                raise Exception("Database connection pool is not initialized")
            
            result = await self._write_records(
                '''
                WITH updated_website AS (
                    INSERT INTO websites (
                        url, program_id, host, port, scheme, techs, favicon_hash, favicon_url
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8
                    )
                    ON CONFLICT (url) DO UPDATE SET
                        host = CASE
                            WHEN EXCLUDED.host IS NOT NULL AND EXCLUDED.host IS DISTINCT FROM websites.host THEN EXCLUDED.host
                            ELSE websites.host
                        END,
                        port = CASE
                            WHEN EXCLUDED.port IS NOT NULL AND EXCLUDED.port IS DISTINCT FROM websites.port THEN EXCLUDED.port
                            ELSE websites.port
                        END,
                        scheme = CASE
                            WHEN EXCLUDED.scheme IS NOT NULL AND EXCLUDED.scheme IS DISTINCT FROM websites.scheme THEN EXCLUDED.scheme
                            ELSE websites.scheme
                        END,
                        techs = CASE
                            WHEN EXCLUDED.techs IS NOT NULL AND EXCLUDED.techs IS DISTINCT FROM websites.techs THEN 
                                CASE
                                    WHEN websites.techs IS NULL THEN EXCLUDED.techs
                                    ELSE (
                                        SELECT ARRAY(
                                            SELECT DISTINCT elem
                                            FROM UNNEST(websites.techs || EXCLUDED.techs) AS elem
                                            WHERE elem IS NOT NULL
                                        )
                                    )
                                END
                            ELSE websites.techs
                        END,
                        program_id = CASE
                            WHEN EXCLUDED.program_id IS NOT NULL AND EXCLUDED.program_id IS DISTINCT FROM websites.program_id THEN EXCLUDED.program_id
                            ELSE websites.program_id
                        END,
                        discovered_at = CASE
                            WHEN EXCLUDED.host IS DISTINCT FROM websites.host OR
                                 EXCLUDED.port IS DISTINCT FROM websites.port OR
                                 EXCLUDED.scheme IS DISTINCT FROM websites.scheme OR
                                 EXCLUDED.techs IS DISTINCT FROM websites.techs OR
                                 EXCLUDED.program_id IS DISTINCT FROM websites.program_id OR
                                 EXCLUDED.favicon_hash IS DISTINCT FROM websites.favicon_hash OR
                                 EXCLUDED.favicon_url IS DISTINCT FROM websites.favicon_url
                            THEN CURRENT_TIMESTAMP
                            ELSE websites.discovered_at
                        END,
                        favicon_hash = CASE
                            WHEN EXCLUDED.favicon_hash IS NOT NULL AND EXCLUDED.favicon_hash IS DISTINCT FROM websites.favicon_hash THEN EXCLUDED.favicon_hash
                            ELSE websites.favicon_hash
                        END,
                        favicon_url = CASE
                            WHEN EXCLUDED.favicon_url IS NOT NULL AND EXCLUDED.favicon_url IS DISTINCT FROM websites.favicon_url THEN EXCLUDED.favicon_url
                            ELSE websites.favicon_url
                        END
                    WHERE
                        (EXCLUDED.host IS NOT NULL AND EXCLUDED.host IS DISTINCT FROM websites.host) OR
                        (EXCLUDED.port IS NOT NULL AND EXCLUDED.port IS DISTINCT FROM websites.port) OR
                        (EXCLUDED.scheme IS NOT NULL AND EXCLUDED.scheme IS DISTINCT FROM websites.scheme) OR
                        (EXCLUDED.techs IS NOT NULL AND EXCLUDED.techs IS DISTINCT FROM websites.techs) OR
                        (EXCLUDED.program_id IS NOT NULL AND EXCLUDED.program_id IS DISTINCT FROM websites.program_id) OR
                        (EXCLUDED.favicon_hash IS NOT NULL AND EXCLUDED.favicon_hash IS DISTINCT FROM websites.favicon_hash) OR
                        (EXCLUDED.favicon_url IS NOT NULL AND EXCLUDED.favicon_url IS DISTINCT FROM websites.favicon_url)
                    RETURNING *, xmax, (xmax = 0) as is_insert
                ), existing_website AS (
                    SELECT id, url, host, port, scheme, techs, program_id, discovered_at, favicon_hash, favicon_url
                    FROM websites 
                    WHERE url = $1 
                    AND NOT EXISTS (SELECT 1 FROM updated_website)
                )
                SELECT 
                    COALESCE(uw.id, ew.id) as id,
                    COALESCE(uw.url, ew.url) as url,
                    COALESCE(uw.host, ew.host) as host,
                    COALESCE(uw.port, ew.port) as port,
                    COALESCE(uw.scheme, ew.scheme) as scheme,
                    COALESCE(uw.techs, ew.techs) as techs,
                    COALESCE(uw.program_id, ew.program_id) as program_id,
                    COALESCE(uw.discovered_at, ew.discovered_at) as discovered_at,
                    COALESCE(uw.favicon_hash, ew.favicon_hash) as favicon_hash,
                    COALESCE(uw.favicon_url, ew.favicon_url) as favicon_url,
                    CASE 
                        WHEN uw.is_insert THEN true
                        WHEN uw.xmax IS NOT NULL THEN false
                        ELSE null
                    END as inserted
                FROM updated_website uw
                FULL OUTER JOIN existing_website ew ON true
                WHERE uw.id IS NOT NULL OR ew.id IS NOT NULL
                LIMIT 1
                ''',
                url.lower(),
                program_id,
                host,
                port,
                scheme,
                techs,
                favicon_hash,
                favicon_url
            )
            
            if result.success and isinstance(result.data, list) and len(result.data) > 0:
                details = f"{url}{f' Host:{host}' if host else ''}{f' Port:{port}' if port else ''}{f' Scheme:{scheme}' if scheme else ''}"
                logger.debug(f"Operation result for website {url}: {result.data[0]}")
                if result.data[0]['inserted'] is True:
                    logger.success(f"RECORD INSERTED [WEBSITE]: {details}")
                elif result.data[0]['inserted'] is False:
                    logger.info(f"RECORD UPDATED [WEBSITE]: {details}")
                elif result.data[0]['inserted'] is None:
                    logger.debug(f"RECORD UNCHANGED [WEBSITE]: {details}")
                else:
                    logger.warning(f"UNEXPECTED STATUS FOR WEBSITE: {details} - Status: {result.data[0]['inserted']}")
                return DbResult(success=True, data=result.data[0])
            else:
                logger.error(f"Failed to insert or update website in database: {result.error}")
                return DbResult(success=False, error=f"Error inserting or updating website in database: {result.error}")
        except Exception as e:
            logger.error(f"Error inserting or updating website in database: {e}")
            logger.exception(e)
            return DbResult(success=False, error=f"Error inserting or updating website in database: {e}")

    async def insert_website_path(
            self, 
            program_id: int,
            website_id: int, 
            path: str, 
            final_path: str = None, 
            techs: List[str] = None, 
            response_time: str = None, 
            lines: int = None, 
            title: str = None, 
            words: int = None, 
            method: str = None, 
            scheme: str = None, 
            status_code: int = None, 
            content_type: str = None, 
            content_length: int = None, 
            chain_status_codes: List[int] = None, 
            page_type: str = None, 
            body_preview: str = None,
            resp_header_hash: str = None,
            resp_body_hash: str = None):
        await self.ensure_connected()
        try:
            if self.pool is None:
                raise Exception("Database connection pool is not initialized")
            
            # First check if record exists and get current values
            existing = await self._fetch_records(
                '''
                SELECT *
                FROM websites_paths 
                WHERE website_id = $1 AND path = $2
                ''',
                website_id, path
            )
            
            if existing.success and existing.data:
                current = existing.data[0]
                # Check if any values would actually change
                needs_update = False
                update_fields = []
                
                if final_path is not None and current['final_path'] != final_path:
                    needs_update = True
                    update_fields.append(f"final_path: {current['final_path']} -> {final_path}")
                if techs is not None and current['techs'] != techs:
                    needs_update = True
                    update_fields.append(f"techs: {current['techs']} -> {techs}")
                if response_time is not None and current['response_time'] != response_time:
                    needs_update = True
                    update_fields.append(f"response_time: {current['response_time']} -> {response_time}")
                if lines is not None and current['lines'] != lines:
                    needs_update = True
                    update_fields.append(f"lines: {current['lines']} -> {lines}")
                if title is not None and current['title'] != title:
                    needs_update = True
                    update_fields.append(f"title: {current['title']} -> {title}")
                if words is not None and current['words'] != words:
                    needs_update = True
                    update_fields.append(f"words: {current['words']} -> {words}")
                if method is not None and current['method'] != method:
                    needs_update = True
                    update_fields.append(f"method: {current['method']} -> {method}")
                if scheme is not None and current['scheme'] != scheme:
                    needs_update = True
                    update_fields.append(f"scheme: {current['scheme']} -> {scheme}")
                if status_code is not None and current['status_code'] != status_code:
                    needs_update = True
                    update_fields.append(f"status_code: {current['status_code']} -> {status_code}")
                if content_type is not None and current['content_type'] != content_type:
                    needs_update = True
                    update_fields.append(f"content_type: {current['content_type']} -> {content_type}")
                if content_length is not None and current['content_length'] != content_length:
                    needs_update = True
                    update_fields.append(f"content_length: {current['content_length']} -> {content_length}")
                if chain_status_codes is not None and current['chain_status_codes'] != chain_status_codes:
                    needs_update = True
                    update_fields.append(f"chain_status_codes: {current['chain_status_codes']} -> {chain_status_codes}")
                if page_type is not None and current['page_type'] != page_type:
                    needs_update = True
                    update_fields.append(f"page_type: {current['page_type']} -> {page_type}")
                if body_preview is not None and current['body_preview'] != body_preview:
                    needs_update = True
                    update_fields.append("body_preview changed")
                if resp_header_hash is not None and current['resp_header_hash'] != resp_header_hash:
                    needs_update = True
                    update_fields.append(f"resp_header_hash: {current['resp_header_hash']} -> {resp_header_hash}")
                if resp_body_hash is not None and current['resp_body_hash'] != resp_body_hash:
                    needs_update = True
                    update_fields.append(f"resp_body_hash: {current['resp_body_hash']} -> {resp_body_hash}")
                
                if not needs_update:
                    details = f"{path} Website:{website_id}"
                    logger.debug(f"RECORD UNCHANGED [WEBSITE PATH]: {details}")
                    return DbResult(success=True, data={'id': current['id'], 'inserted': None})

            result = await self._write_records(
                '''
                WITH updated_path AS (
                    INSERT INTO websites_paths (
                        website_id, path, final_path, techs, response_time, lines, title, words, method, scheme, 
                        status_code, content_type, content_length, chain_status_codes, page_type, body_preview, 
                        resp_header_hash, resp_body_hash, program_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                    ON CONFLICT (website_id, path) DO UPDATE SET
                        final_path = EXCLUDED.final_path,
                        techs = EXCLUDED.techs,
                        response_time = EXCLUDED.response_time,
                        lines = EXCLUDED.lines,
                        title = EXCLUDED.title,
                        words = EXCLUDED.words,
                        method = EXCLUDED.method,
                        scheme = EXCLUDED.scheme,
                        status_code = EXCLUDED.status_code,
                        content_type = EXCLUDED.content_type,
                        content_length = EXCLUDED.content_length,
                        chain_status_codes = EXCLUDED.chain_status_codes,
                        page_type = EXCLUDED.page_type,
                        body_preview = EXCLUDED.body_preview,
                        resp_header_hash = EXCLUDED.resp_header_hash,
                        resp_body_hash = EXCLUDED.resp_body_hash,
                        program_id = EXCLUDED.program_id
                    WHERE (
                        EXCLUDED.final_path IS DISTINCT FROM websites_paths.final_path OR
                        EXCLUDED.techs IS DISTINCT FROM websites_paths.techs OR
                        EXCLUDED.response_time IS DISTINCT FROM websites_paths.response_time OR
                        EXCLUDED.lines IS DISTINCT FROM websites_paths.lines OR
                        EXCLUDED.title IS DISTINCT FROM websites_paths.title OR
                        EXCLUDED.words IS DISTINCT FROM websites_paths.words OR
                        EXCLUDED.method IS DISTINCT FROM websites_paths.method OR
                        EXCLUDED.scheme IS DISTINCT FROM websites_paths.scheme OR
                        EXCLUDED.status_code IS DISTINCT FROM websites_paths.status_code OR
                        EXCLUDED.content_type IS DISTINCT FROM websites_paths.content_type OR
                        EXCLUDED.content_length IS DISTINCT FROM websites_paths.content_length OR
                        EXCLUDED.chain_status_codes IS DISTINCT FROM websites_paths.chain_status_codes OR
                        EXCLUDED.page_type IS DISTINCT FROM websites_paths.page_type OR
                        EXCLUDED.body_preview IS DISTINCT FROM websites_paths.body_preview OR
                        EXCLUDED.resp_header_hash IS DISTINCT FROM websites_paths.resp_header_hash OR
                        EXCLUDED.resp_body_hash IS DISTINCT FROM websites_paths.resp_body_hash OR
                        EXCLUDED.program_id IS DISTINCT FROM websites_paths.program_id
                    )
                    RETURNING *, xmax, (xmax = 0) as is_insert
                ), existing_path AS (
                    SELECT id
                    FROM websites_paths 
                    WHERE website_id = $1 AND path = $2
                    AND NOT EXISTS (SELECT 1 FROM updated_path)
                )
                SELECT 
                    COALESCE(up.id, ep.id) as id,
                    CASE 
                        WHEN up.is_insert THEN true
                        WHEN up.xmax IS NOT NULL THEN false
                        ELSE null
                    END as inserted
                FROM updated_path up
                FULL OUTER JOIN existing_path ep ON true
                WHERE up.id IS NOT NULL OR ep.id IS NOT NULL
                LIMIT 1
                ''',
                website_id,
                path,
                final_path,
                techs,
                response_time,
                lines,
                title,
                words,
                method,
                scheme,
                status_code,
                content_type,
                content_length,
                chain_status_codes,
                page_type,
                body_preview,
                resp_header_hash,
                resp_body_hash,
                program_id
            )
            
            if result.success and isinstance(result.data, list) and len(result.data) > 0:
                details = f"{path} Website:{website_id}"
                logger.debug(f"Operation result for website path {path}: {result.data[0]}")
                
                if result.data[0]['inserted'] is True:
                    logger.success(f"RECORD INSERTED [WEBSITE PATH]: {details}")
                elif result.data[0]['inserted'] is False:
                    logger.info(f"RECORD UPDATED [WEBSITE PATH]: {details} - Changes: {', '.join(update_fields)}")
                else:
                    logger.debug(f"RECORD UNCHANGED [WEBSITE PATH]: {details}")
                
                return DbResult(success=True, data=result.data[0])
            else:
                return DbResult(success=False, error=f"Error inserting or updating website path in database: {result.error}")
        except Exception as e:
            logger.error(f"Error inserting or updating website path in database: {e}")
            return DbResult(success=False, error=f"Error inserting or updating website path in database: {e}")

    async def insert_certificate(self, program_id: int, data: Dict[str, Any]):
        await self.ensure_connected()
        logger.debug(f"Entering insert_certificate for program {program_id}: {data}")
        try:
            if self.pool is None:
                raise Exception("Database connection pool is not initialized")
            
            # Convert ISO format strings to timezone-aware datetime objects
            valid_date = dateutil.parser.parse(data.get('cert', {}).get('valid_date')).replace(tzinfo=None) if data.get('cert', {}).get('valid_date') else None
            expiry_date = dateutil.parser.parse(data.get('cert', {}).get('expiry_date')).replace(tzinfo=None) if data.get('cert', {}).get('expiry_date') else None
            
            # Convert types before insertion
            website_id = await self._fetch_value('''
                SELECT id FROM websites WHERE url = $1
            ''', data.get("url"))
            logger.debug(f"Website ID: {website_id}")
            website_id = website_id.data
            subject_dn = data.get("cert", {}).get('subject_dn')
            subject_cn = data.get("cert", {}).get('subject_cn')
            subject_an = data.get("cert", {}).get('subject_an')
            issuer_dn = data.get("cert", {}).get('issuer_dn')
            issuer_cn = data.get("cert", {}).get('issuer_cn')
            issuer_org = data.get("cert", {}).get('issuer_org')
            if issuer_org:
                issuer_org = issuer_org[0]
            else:
                issuer_org = None
            
            serial = data.get("cert", {}).get('serial')
            fingerprint_hash = data.get("cert", {}).get('fingerprint_hash')

            result = await self._write_records(
                '''
                INSERT INTO certificates (
                        website_id, subject_dn, subject_cn, subject_an, valid_date, expiry_date, issuer_dn, issuer_cn, issuer_org, serial, fingerprint_hash, program_id
                    )
                    VALUES (
                        ARRAY[$1]::integer[], $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                    )
                    ON CONFLICT (serial) DO UPDATE SET 
                        website_id = CASE 
                            WHEN $1 = ANY(certificates.website_id) THEN certificates.website_id
                            WHEN EXCLUDED.website_id IS NOT NULL THEN array_append(certificates.website_id, $1)
                            ELSE certificates.website_id
                        END,
                        subject_dn = CASE
                            WHEN EXCLUDED.subject_dn IS NOT NULL THEN EXCLUDED.subject_dn
                            ELSE certificates.subject_dn
                        END,
                        subject_cn = CASE
                            WHEN EXCLUDED.subject_cn IS NOT NULL THEN EXCLUDED.subject_cn
                            ELSE certificates.subject_cn
                        END,
                        subject_an = CASE
                            WHEN EXCLUDED.subject_an IS NOT NULL THEN EXCLUDED.subject_an
                            ELSE certificates.subject_an
                        END,
                        valid_date = CASE
                            WHEN EXCLUDED.valid_date IS NOT NULL THEN EXCLUDED.valid_date
                            ELSE certificates.valid_date
                        END,
                        expiry_date = CASE
                            WHEN EXCLUDED.expiry_date IS NOT NULL THEN EXCLUDED.expiry_date
                            ELSE certificates.expiry_date
                        END,
                        issuer_dn = CASE
                            WHEN EXCLUDED.issuer_dn IS NOT NULL THEN EXCLUDED.issuer_dn
                            ELSE certificates.issuer_dn
                        END,
                        issuer_cn = CASE
                            WHEN EXCLUDED.issuer_cn IS NOT NULL THEN EXCLUDED.issuer_cn
                            ELSE certificates.issuer_cn
                        END,
                        issuer_org = CASE
                            WHEN EXCLUDED.issuer_org IS NOT NULL THEN EXCLUDED.issuer_org
                            ELSE certificates.issuer_org
                        END,
                        fingerprint_hash = CASE
                            WHEN EXCLUDED.fingerprint_hash IS NOT NULL THEN EXCLUDED.fingerprint_hash
                            ELSE certificates.fingerprint_hash
                        END,
                        program_id = CASE
                            WHEN EXCLUDED.program_id IS NOT NULL THEN EXCLUDED.program_id
                            ELSE certificates.program_id
                        END
                    RETURNING (xmax = 0) AS inserted
                ''',
                website_id,
                subject_dn,
                subject_cn,
                subject_an,
                valid_date,
                expiry_date,
                issuer_dn,
                issuer_cn,
                issuer_org,
                serial,
                fingerprint_hash,
                int(program_id)
            )
            
            if result.success:
                if result.data[0]['inserted']:
                    logger.success(f"RECORD INSERTED [CERTIFICATE]: {serial}")
                else:
                    logger.info(f"RECORD UPDATED [CERTIFICATE]: {serial}")
                return DbResult(success=True, data=result.data[0])
            return DbResult(success=False, error=f"Error inserting or updating certificate in database: {result.error}")
        except Exception as e:
            logger.error(f"Error inserting or updating certificate in database: {e}")
            logger.exception(e)
            return DbResult(success=False, error=f"Error inserting or updating certificate in database: {e}")

    async def insert_nuclei(self, program_id: int, data: Dict[str, Any]):
        await self.ensure_connected()
        logger.debug(f"Entering insert_nuclei for program {program_id}: {data}")
        try:
            if self.pool is None:
                raise Exception("Database connection pool is not initialized")
            
            # Convert types before insertion
            url = data.get('url')
            matched_at = data.get('matched_at')
            matcher_name = data.get('matcher_name')
            template_id = data.get('template_id')
            template_name = data.get('template_name')
            template_path = data.get('template_path')
            severity = data.get('severity')
            type = data.get('type')
            port = data.get('port')
            ip = data.get('ip')

            result = await self._write_records(
                '''
                INSERT INTO nuclei (
                        url, matched_at, type, ip, port, template_path, template_id, template_name, severity, program_id, matcher_name
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                    )
                    ON CONFLICT (url, template_id) DO UPDATE SET
                        matched_at = CASE
                            WHEN EXCLUDED.matched_at IS NOT NULL THEN EXCLUDED.matched_at
                            ELSE nuclei.matched_at
                        END,
                        type = CASE
                            WHEN EXCLUDED.type IS NOT NULL THEN EXCLUDED.type
                            ELSE nuclei.type
                        END,
                        ip = CASE
                            WHEN EXCLUDED.ip IS NOT NULL THEN EXCLUDED.ip
                            ELSE nuclei.ip
                        END,
                        port = CASE
                            WHEN EXCLUDED.port IS NOT NULL THEN EXCLUDED.port
                            ELSE nuclei.port
                        END,
                        template_path = CASE
                            WHEN EXCLUDED.template_path IS NOT NULL THEN EXCLUDED.template_path
                            ELSE nuclei.template_path
                        END,
                        template_name = CASE
                            WHEN EXCLUDED.template_name IS NOT NULL THEN EXCLUDED.template_name
                            ELSE nuclei.template_name
                        END,
                        severity = CASE
                            WHEN EXCLUDED.severity IS NOT NULL THEN EXCLUDED.severity
                            ELSE nuclei.severity
                        END,
                        matcher_name = CASE
                            WHEN EXCLUDED.matcher_name IS NOT NULL THEN EXCLUDED.matcher_name
                            ELSE nuclei.matcher_name
                        END,
                        program_id = CASE
                            WHEN EXCLUDED.program_id IS NOT NULL THEN EXCLUDED.program_id
                            ELSE nuclei.program_id
                        END
                    RETURNING (xmax = 0) AS inserted
                ''',
                str(url),
                matched_at,
                str(type),
                str(ip),
                int(port),
                template_path,
                template_id,
                template_name,
                severity,
                program_id,
                matcher_name
            )
            
            if result.success:
                if result.data[0]['inserted']:
                    logger.success(f"RECORD INSERTED [NUCLEI]: {url} {template_id}")
                else:
                    logger.info(f"RECORD UPDATED [NUCLEI]: {url} {template_id}")
                return DbResult(success=True, data=result.data[0])
            return DbResult(success=False, error=f"Error inserting or updating Nuclei hit in database: {result.error}")
        except Exception as e:
            logger.error(f"Error inserting or updating Nuclei hit in database: {e}")
            logger.exception(e)
            return DbResult(success=False, error=f"Error inserting or updating Nuclei hit in database: {e}")

    async def get_domain(self, domain: str) -> Dict[str, Any]:
        """
        Get existing domain data.
        
        Args:
            domain (str): Domain to retrieve
        
        Returns:
            Dict[str, Any]: Domain data or None if not found
        """
        result = await self._fetch_records(
            'SELECT * FROM domains WHERE domain = $1',
            domain.lower()
        )
        if result.success and result.data:
            return result.data[0]
        return None

    async def log_reconworker_operation(self, execution_id: str, component_id: str, function_name: str, program_id: int, target: str, parameters: Dict[str, Any], status: str, error_message: str = None, completed_at: datetime = None) -> bool:
        """Log worker function execution."""
        try:
            query = """
            INSERT INTO recon_logs (execution_id, component_id, function_name, program_id, target, parameters, status, error_message, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (execution_id, status) DO NOTHING
            """
            result = await self._write_records(
                query,
                execution_id,
                component_id,
                function_name,
                program_id,
                target,
                json.dumps(parameters),
                status,
                error_message,
                completed_at
            )
            return result
        except Exception as e:
            logger.error(f"Error logging worker execution: {str(e)}")
            return DbResult(success=False, error=f"Error logging worker execution: {str(e)}")

    async def log_parsingworker_operation(self, component_id: str, message_id: str, message_type: str, program_id: int, 
                                     message_data: Dict[str, Any], status: str, processing_result: Dict[str, Any] = None, 
                                     actions_taken: Dict[str, Any] = None, error_message: str = None, processed_at: datetime = None) -> bool:
        """Log job processor message handling."""
        try:
            query = """
            INSERT INTO parsing_logs (component_id, message_id, message_type, program_id, message_data, 
                                         processing_result, actions_taken, status, error_message, processed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """
            result = await self._write_records(
                query,
                component_id,
                message_id,
                message_type,
                program_id,
                json.dumps(message_data),
                json.dumps(processing_result) if processing_result else None,
                json.dumps(actions_taken) if actions_taken else None,
                status,
                error_message,
                processed_at
            )
            return DbResult(success=result.success, data=result.data)
        except Exception as e:
            logger.error(f"Error logging job processor message: {str(e)}")
            return DbResult(success=False, error=f"Error logging job processor message: {str(e)}")

    async def log_dataworker_operation(self, component_id: str, data_type: str, program_id: int, operation_type: str, 
                                        data: Dict[str, Any], status: str, result: Dict[str, Any] = None, 
                                        error_message: str = None, completed_at: datetime = None) -> bool:
        """Log data processor operations."""
        try:
            query = """
            INSERT INTO data_logs (component_id, data_type, program_id, operation_type, data, 
                                          result, status, error_message, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """
            result = await self._write_records(
                query,
                component_id,
                data_type,
                program_id,
                operation_type,
                json.dumps(data),
                json.dumps(result) if result else None,
                status,
                error_message,
                completed_at
            )
            return DbResult(success=result.success, data=result.data)
        except Exception as e:
            logger.error(f"Error logging data processor operation: {str(e)}")
            return DbResult(success=False, error=f"Error logging data processor operation: {str(e)}")