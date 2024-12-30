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
            scope_count = await self._fetch_value('SELECT COUNT(*) FROM program_scopes WHERE program_id = $1', program_id)
            if not self._regex_cache[program_id] or len(self._regex_cache[program_id]) < scope_count.data:
                logger.debug(f"Regex cache for program_id {program_id} is empty or has fewer regexes than scope count. Refreshing...")
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

    async def insert_ip(self, ip: str, ptr: str, cloud_provider: str, program_id: int) -> Dict[str, Any]:
        # Validate IP address is IPv4 or IPv6
        import ipaddress
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            logger.error(f"Invalid IP address: {ip}")
            return {'inserted': False, 'id': None}

        query = """
        INSERT INTO ips (ip, ptr, cloud_provider, program_id)
        VALUES ($1, LOWER($2), $3, $4)
        ON CONFLICT (ip) DO UPDATE
        SET ptr = CASE
                WHEN EXCLUDED.ptr IS NOT NULL AND EXCLUDED.ptr <> '' THEN EXCLUDED.ptr
                ELSE ips.ptr
            END,
            cloud_provider = CASE
                WHEN EXCLUDED.cloud_provider IS NOT NULL AND EXCLUDED.cloud_provider <> '' THEN EXCLUDED.cloud_provider
                ELSE ips.cloud_provider
            END,
            program_id = EXCLUDED.program_id,
            discovered_at = CURRENT_TIMESTAMP
        RETURNING (xmax = 0) AS inserted, id
        """
        try:
            result = await self._write_records(query, ip, ptr, cloud_provider, program_id)
            logger.debug(f"Insert result: {result}")
            if result.success and isinstance(result.data, list) and len(result.data) > 0:
                return {
                    'inserted': result.data[0]['inserted'],
                    'id': result.data[0]['id']
                }
            return {'inserted': False, 'id': None}
        except Exception as e:
            logger.error(f"Error inserting or updating IP in database: {str(e)}")
            logger.exception(e)
            return {'inserted': False, 'id': None}
    
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
    
    async def insert_domain(self, domain: str, program_id: int, ips: List[str] = None, cnames: List[str] = None, is_catchall: bool = False) -> Dict[str, Any]:
        try:
            logger.debug(f"insert_domain called with is_catchall={is_catchall}, type={type(is_catchall)}")
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
                    VALUES ($1, $2, $3, $4, $5::boolean) 
                    ON CONFLICT (domain) DO UPDATE 
                    SET program_id = EXCLUDED.program_id, 
                        ips = EXCLUDED.ips, 
                        cnames = EXCLUDED.cnames, 
                        is_catchall = EXCLUDED.is_catchall::boolean
                    RETURNING (xmax = 0) AS inserted, is_catchall, id
                    ''',
                    domain.lower(),
                    program_id,
                    ip_ids,
                    [c.lower() for c in cnames] if cnames else None,
                    is_catchall
                )
                logger.debug(f"Insert result: {result}")
                
                if result.success and isinstance(result.data, list) and len(result.data) > 0:
                    return {
                        'inserted': result.data[0]['inserted'],
                        'id': result.data[0]['id']
                    }
                return {'inserted': False, 'id': None}
            else:
                return {'inserted': False, 'id': None}
        except Exception as e:
            logger.error(f"Error inserting or updating domain in database: {str(e)}")
            logger.exception(e)
            return {'inserted': False, 'id': None}
    
    async def insert_url(self, url: str, httpx_data: Dict[str, Any], program_id: int):
        logger.debug(f"{url}:{httpx_data}")
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
                        cdn_name, cdn_type, final_url, timestamp,
                        webserver, status_code, content_type, content_length,
                        chain_status_codes, page_type, body_preview
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                        $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26
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
                        timestamp = EXCLUDED.timestamp,
                        webserver = EXCLUDED.webserver,
                        status_code = EXCLUDED.status_code,
                        content_type = EXCLUDED.content_type,
                        content_length = EXCLUDED.content_length,
                        chain_status_codes = EXCLUDED.chain_status_codes,
                        page_type = EXCLUDED.page_type,
                        body_preview = EXCLUDED.body_preview
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
                timestamp,
                httpx_data.get('webserver'),
                status_code,
                httpx_data.get('content_type'),
                content_length,
                httpx_data.get('chain_status_codes'),
                httpx_data.get('knowledgebase', {}).get('PageType'),
                httpx_data.get('body_preview')
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
                return data[0]
            return False
        except Exception as e:
            logger.error(f"Error inserting or updating URL in database: {e}")
            logger.exception(e)
            return False
    
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
            url_id = await self._fetch_value('''
                SELECT id FROM urls WHERE url = $1
            ''', data.get("url"))
            logger.debug(f"URL ID: {url_id}")
            url_id = url_id.data
            subject_dn = data.get("cert", {}).get('subject_dn')
            subject_cn = data.get("cert", {}).get('subject_cn')
            subject_an = data.get("cert", {}).get('subject_an')
            issuer_dn = data.get("cert", {}).get('issuer_dn')
            issuer_cn = data.get("cert", {}).get('issuer_cn')
            issuer_org = data.get("cert", {}).get('issuer_org')[0]
            serial = data.get("cert", {}).get('serial')
            fingerprint_hash = data.get("cert", {}).get('fingerprint_hash')

            result = await self._write_records(
                '''
                INSERT INTO certificates (
                        url_id, subject_dn, subject_cn, subject_an, valid_date, expiry_date, issuer_dn, issuer_cn, issuer_org, serial, fingerprint_hash, program_id
                    )
                    VALUES (
                        ARRAY[$1]::integer[], $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                    )
                    ON CONFLICT (serial) DO UPDATE SET url_id =
                        CASE 
                            WHEN $1 = ANY(certificates.url_id) THEN certificates.url_id
                            ELSE array_append(certificates.url_id, $1)
                        END
                    RETURNING (xmax = 0) AS inserted
                ''',
                url_id,
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
            
            # Handle nested DbResult objects
            if result.success and isinstance(result.data, DbResult):
                data = result.data.data
            else:
                data = result.data

            if data and isinstance(data, list) and len(data) > 0:
                return data[0]['inserted']
            return False
        except Exception as e:
            logger.error(f"Error inserting or updating certificate in database: {e}")
            logger.exception(e)
            return False


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
                        matched_at = EXCLUDED.matched_at,
                        type = EXCLUDED.type,
                        ip = EXCLUDED.ip,
                        port = EXCLUDED.port,
                        template_path = EXCLUDED.template_path,
                        template_name = EXCLUDED.template_name,
                        severity = EXCLUDED.severity,
                        matcher_name = EXCLUDED.matcher_name,
                        program_id = EXCLUDED.program_id
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
            
            # Handle nested DbResult objects
            if result.success and isinstance(result.data, DbResult):
                data = result.data.data
            else:
                data = result.data

            if data and isinstance(data, list) and len(data) > 0:
                inserted = data[0]['inserted']
                if inserted:
                   logger.info(f"New Nuclei hit inserted: {url}")
                else:
                   logger.info(f"Nuclei hit updated: {url}")
                return inserted
            return False
        except Exception as e:
            logger.error(f"Error inserting or updating Nuclei hit in database: {e}")
            logger.exception(e)
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
            return result.success
        except Exception as e:
            logger.error(f"Error logging worker execution: {str(e)}")
            return False

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
            return result.success
        except Exception as e:
            logger.error(f"Error logging job processor message: {str(e)}")
            return False

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
            return result.success
        except Exception as e:
            logger.error(f"Error logging data processor operation: {str(e)}")
            return False