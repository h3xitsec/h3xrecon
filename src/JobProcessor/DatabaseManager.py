from typing import List, Dict, Any, Optional, Union
import asyncpg
import re
import os
from loguru import logger
import json
from datetime import datetime
import uuid
from typing import Dict, Any, Union

# Database configuration
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
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return []
    
    async def check_domain_program(self, domain: str) -> Optional[str]:
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT p.name, ps.regex
                    FROM programs p
                    JOIN program_scopes ps ON p.id = ps.program_id
                ''')
                
                for row in rows:
                    program_name, regex = row['name'], row['regex']
                    if re.match(regex, domain):
                        return program_name
                
                return None
        except Exception as e:
            logger.error(f"Error checking domain program: {e}")
            return None
    
    async def insert_out_of_scope_domain(self, domain: str, program_id: int):
        await self.ensure_connected()
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO out_of_scope_domains (domain, program_ids)
                    VALUES ($1, ARRAY[$2])
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

    async def insert_domain(self, domain: Union[str, Dict[str, str]], program_id: int, ips: List[int] = None):
        try:
            if isinstance(domain, dict) and 'subdomain' in domain:
                domain = domain['subdomain']
            
            if not isinstance(domain, str):
                logger.warning(f"Attempted to insert non-string domain: {domain}, type: {type(domain)}")
                return

            if await self.check_domain_regex_match(domain, program_id):
                async with self.pool.acquire() as conn:
                    result = await conn.fetchrow(
                        '''
                        INSERT INTO domains (domain, program_id, ips) 
                        VALUES ($1, $2, $3) 
                        ON CONFLICT (domain) DO UPDATE 
                        SET program_id = EXCLUDED.program_id, ips = EXCLUDED.ips
                        RETURNING (xmax = 0) AS inserted
                        ''',
                        domain, program_id, ips
                    )
                    if result['inserted']:
                        logger.info(f"New domain inserted: {domain}")
            else:
                logger.warning(f"Domain {domain} does not match any regex for program {program_id}")
        except Exception as e:
            logger.error(f"Error inserting or updating domain in database: {str(e)}")
            logger.exception(e)

    async def insert_url(self, url: str, title: str, chain_status_codes: List[int], status_code: int, final_url: str, program_id: int, scheme: str, port: int, webserver: str, content_type: str, content_length: int, tech: List[str]):
        await self.ensure_connected()
        try:
            if self.pool is None:
                raise Exception("Database connection pool is not initialized")
            
            async with self.pool.acquire() as conn:
                url_exists = await conn.fetchval(
                    'SELECT EXISTS(SELECT 1 FROM urls WHERE url = $1)',
                    url
                )
                if not url_exists:
                    await conn.execute(
                        'INSERT INTO urls (url, title, chain_status_codes, status_code, final_url, program_id, scheme, port, webserver, content_type, content_length, tech) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)',
                        url, title, chain_status_codes, status_code, final_url, program_id, scheme, int(port) if port is not None else None, webserver, content_type, content_length, tech
                    )
                    logger.info(f"New URL inserted: {url}")
        except Exception as e:
            logger.error(f"Error inserting URL into database: {e}")
    
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

    async def insert_ip(self, ip: str, domain: str, program_id: int):
        try:
            if not await self.check_ip_pattern_match(ip):
                logger.warning(f"Invalid IP format: {ip}. Skipping insertion.")
                return

            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO ips (ip, program_id) 
                    VALUES ($1, $2) 
                    ON CONFLICT (ip) DO NOTHING
                ''', ip, program_id)
            logger.info(f"Inserted/Updated IP {ip} in program {program_id}")
        except Exception as e:
            logger.error(f"Error inserting IP into database: {str(e)}")
            logger.exception(e)

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


