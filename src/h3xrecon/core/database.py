import asyncpg
import os
import json
import re
import asyncpg
import uuid
from typing import List, Dict, Any
from loguru import logger
from datetime import datetime
from .config import Config

class DatabaseManager:
    def __init__(self, config: Config = None):
        if config is None:
            self.config = Config().database.to_dict()
        else:
            self.config = config
        self.pool = None

    async def ensure_connected(self):
        if self.pool is None:
            await self.connect()

    async def connect(self):
        self.pool = await asyncpg.create_pool(**self.config)

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
            result = await self.execute_query(query, program_name)
        else:
            query += " GROUP BY d.domain"
            result = await self.execute_query(query)
        return await self.format_json_output(result)

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
            result = await self.execute_query(query, program_name)
        else:
            result = await self.execute_query(query)
        return await self.format_json_output(result)

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
            result = await self.execute_query(query, program_name)
        else:
            result = await self.execute_query(query)
        return await self.format_json_output(result)

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
            result = await self.execute_query(query, program_name)
        else:
            result = await self.execute_query(query)
        return await self.format_json_output(result)

    async def check_domain_regex_match(self, domain: str, program_id: int) -> bool:
        await self.ensure_connected()
        try:
            if isinstance(domain, dict) and 'subdomain' in domain:
                domain = domain['subdomain']
            
            if not isinstance(domain, str):
                logger.warning(f"Domain is not a string: {domain}, type: {type(domain)}")
                return False

            async with self.pool.acquire() as conn:
                program_regexes = await conn.fetch(
                    'SELECT regex FROM program_scopes WHERE program_id = $1',
                    program_id
                )
                for row in program_regexes:
                    regex = row['regex']
                    if not isinstance(regex, str):
                        logger.warning(f"Regex is not a string: {regex}, type: {type(regex)}")
                        continue
                    try:
                        if re.match(regex, domain):
                            return True
                    except re.error as e:
                        logger.error(f"Invalid regex pattern: {regex}. Error: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Error checking domain regex match: {str(e)}")
            logger.exception(e)
            return False

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

    async def remove_program(self, program_name: str):
        """Remove a program and all its associated data"""
        query = """
        DELETE FROM programs 
        WHERE name = $1
        RETURNING id
        """
        result = await self.execute_query(query, program_name)
        if result:
            logger.info(f"Program removed: {program_name}")
            return True
        return False

    async def remove_program_scope(self, program_name: str, scope: str):
        """Remove a specific scope regex from a program"""
        query = """
        DELETE FROM program_scopes 
        WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        AND regex = $2
        RETURNING id
        """
        result = await self.execute_query(query, program_name, scope)
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
        result = await self.execute_query(query, program_name, cidr)
        if result:
            logger.info(f"CIDR removed from program {program_name}: {cidr}")
            return True
        return False

    async def get_ips(self, program_name: str = None):
        print(program_name)
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


    async def insert_service(self, ip: str, program_id: int, port: int = None, protocol: str = None, service: str = None):
        """
        Insert or update a service in the database.
        
        Args:
            ip (str): IP address of the service
            program_id (int): ID of the program this service belongs to
            port (int, optional): Port number of the service
            protocol (str, optional): Protocol used by the service
            service (str, optional): Service provided
        
        Returns:
            bool: True if a new service was inserted, False if an existing service was updated
        """
        await self.ensure_connected()
        if self.pool is None:
            raise Exception("Database connection pool is not initialized")
        
        try:
            async with self.pool.acquire() as conn:
                # First get or create the IP record
                ip_record = await conn.fetchrow(
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
                
                if not ip_record:
                    raise Exception(f"Failed to insert or get IP record for {ip}")
                    
                ip_id = ip_record['id']

                # Use the ON CONFLICT for services with ports
                result = await conn.fetchrow(
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
                
                service_desc = f"{protocol or 'unknown'}:{ip}:{port if port else 'no_port'}"
                if result['inserted']:
                    logger.info(f"New service inserted: {service_desc}")
                else:
                    logger.info(f"Service updated: {service_desc}")
                    
                return result['inserted']
                
        except Exception as e:
            logger.error(f"Error inserting or updating service in database: {str(e)}")
            logger.exception(e)
            raise  # Re-raise the exception after logging
    
    async def insert_domain(self, domain: str, program_id: int, ips: List[str] = None, cnames: List[str] = None, is_catchall: bool = False):
       #logger.debug(f"Inserting domain: {domain}:{ips}:{cnames} into program {program_id}")
        await self.ensure_connected()
        if self.pool is None:
            raise Exception("Database connection pool is not initialized")
        try:
            if await self.check_domain_regex_match(domain, program_id):
                async with self.pool.acquire() as conn:
                    # Get IP IDs
                    ip_ids = []
                    if ips:
                        for ip in ips:
                            ip_id = await conn.fetchval('SELECT id FROM ips WHERE ip = $1', ip)
                            if ip_id:
                                ip_ids.append(ip_id)
                    
                    result = await conn.fetchrow(
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
                    if result['inserted']:
                        logger.info(f"New domain inserted: {domain}")
                    else:
                        logger.info(f"Domain already exists: {domain}")
                    return result['inserted']
            else:
                logger.warning(f"Domain {domain} does not match any regex for program {program_id}")
                await self.insert_out_of_scope_domain(domain, program_id)
        except Exception as e:
            logger.error(f"Error inserting or updating domain in database: {str(e)}")
            logger.exception(e)
        
    async def insert_out_of_scope_domain(self, domain: str, program_id: int):
        if domain:
            await self.ensure_connected()
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute('''
                        INSERT INTO out_of_scope_domains (domain, program_ids)
                        VALUES ($1, ARRAY[$2::integer])
                        ON CONFLICT (domain) 
                        DO UPDATE SET program_ids = 
                            CASE 
                                WHEN $2::integer = ANY(out_of_scope_domains.program_ids) THEN out_of_scope_domains.program_ids
                                ELSE array_append(out_of_scope_domains.program_ids, $2::integer)
                            END
                    ''', domain.lower(), program_id)
                    logger.info(f"Out-of-scope domain inserted/updated: {domain} for program {program_id}")
            except Exception as e:
                logger.error(f"Error inserting/updating out-of-scope domain in database: {str(e)}")
                logger.exception(e)
                
#    async def insert_url(self, url: str, title: str, chain_status_codes: List[int], status_code: int, final_url: str, program_id: int, scheme: str, port: int, webserver: str, content_type: str, content_length: int, tech: List[str]):
    async def insert_url(self, url: str, httpx_data: Dict[str, Any], program_id: int):
        logger.debug(f"{url}:{httpx_data}")
        await self.ensure_connected()
        try:
            if self.pool is None:
                raise Exception("Database connection pool is not initialized")
            
            async with self.pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO urls (url, httpx_data, program_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (url) DO UPDATE
                    SET httpx_data = COALESCE(NULLIF(EXCLUDED.httpx_data, '{}'), urls.httpx_data)
                    ''',
                    url.lower(),
                    json.dumps(httpx_data),
                    program_id
                )
                logger.info(f"URL inserted or updated: {url}")
        except Exception as e:
            logger.error(f"Error inserting or updating URL in database: {e}")
            logger.exception(e)
    
    async def check_ip_pattern_match(self, ip: str) -> bool:
        #logger.debug(f"Checking IP pattern match for {ip}")
        try:
            ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
            if re.match(ip_pattern, ip):
                octets = ip.split('.')
                return all(0 <= int(octet) <= 255 for octet in octets)
            return False
        except Exception as e:
            logger.error(f"Error checking IP pattern match: {e}")
            return False

    async def insert_ip(self, ip: str, ptr: str, program_id: int) -> int:
        await self.ensure_connected()
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
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(query, ip, ptr, program_id)
                id, inserted = result['id'], result['inserted']
                logger.info(f"IP {'inserted' if inserted else 'updated'}: {ip}")
            return inserted
        except Exception as e:
            logger.error(f"Error inserting IP: {e}")
            raise

    async def log_or_update_function_execution(self, log_entry: Dict[str, Any]):
        await self.ensure_connected()
        try:
            async with self.pool.acquire() as conn:
                # Check if the execution already exists
                existing = await conn.fetchrow('''
                    SELECT * FROM function_logs 
                    WHERE execution_id = $1
                ''', uuid.UUID(log_entry['execution_id']))

                if existing:
                    # Update existing log entry
                    await conn.execute('''
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
                    await conn.execute('''
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
        await self.ensure_connected()
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
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
    
    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        logger.debug(f"Executing query: {query} with args: {args}")
        await self.ensure_connected()
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return []

    async def remove_domain(self, program_name: str, domain: str):
        """Remove a specific domain from a program"""
        query = """
        DELETE FROM domains 
        WHERE program_id = (SELECT id FROM programs WHERE name = $1)
        AND domain = $2
        RETURNING id
        """
        result = await self.execute_query(query, program_name, domain)
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
        result = await self.execute_query(query, program_name, ip)
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
        result = await self.execute_query(query, program_name, url)
        if result:
            logger.info(f"URL removed from program {program_name}: {url}")
            return True
        return False
