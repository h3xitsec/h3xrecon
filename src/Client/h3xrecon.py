import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from tabulate import tabulate
import json
from typing import List, Dict, Any, Optional
import sys
import os
from datetime import datetime, timedelta
import asyncio
from nats.aio.client import Client as NATS

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from QueueManager import QueueManager

class H3XReconClient:
    def __init__(self, host=os.getenv("H3XRECON_DB_HOST"), port=5432, dbname="h3xrecon", user="h3xrecon", password="h3xrecon"):
        self.conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        self.conn.autocommit = True
        self.nc = NATS()
        self.qm = QueueManager()

    # Existing methods...

    async def send_job(self, function_name: str, program_name: str, target: str, force: bool):
        """Send a job to the worker using QueueManager"""
        program_id = self.get_program_id(program_name)
        if not program_id:
            print(f"Error: Program '{program_name}' not found")
            return

        message = {
            "force": force,
            "function": function_name,
            "program_id": program_id,
            "params": {"target": target}
        }

        await self.qm.connect()
        await self.qm.publish_message(
            subject="function.execute",
            stream="FUNCTION_EXECUTE",
            message=message
        )
        await self.qm.close()
        print(f"Job sent: {message}")

    def get_program_id(self, program_name: str) -> Optional[int]:
        """Get program ID by name"""
        query = "SELECT id FROM programs WHERE name = %s"
        result = self.execute_query(query, (program_name,))
        if result:
            return result[0]['id']
        return None

    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute a query with optional parameters"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                if params:
                    cur.execute(query, params)
                else:
                    cur.execute(query)
                return cur.fetchall()
            except Exception as e:
                print(f"Query execution error: {str(e)}")
                print(f"Query: {query}")
                print(f"Params: {params}")
                return []

    async def get_stream_info(self, stream_name: str = None):
        """Get information about NATS streams"""
        try:
            # Initialize NATS options with timeout and max reconnect attempts
            options = {
                "servers": ["nats://100.111.235.28:4222"],
                "connect_timeout": 5,  # 5 seconds timeout
                "max_reconnect_attempts": 3
            }
            
            await self.nc.connect(**options)
            js = self.nc.jetstream()
            
            if stream_name:
                # Get info for specific stream
                stream = await js.stream_info(stream_name)
                consumers = await js.consumers_info(stream_name)
                
                # Calculate unprocessed messages across all consumers
                unprocessed_messages = 0
                for consumer in consumers:
                    unprocessed_messages += consumer.num_pending
                
                return [{
                    "stream": stream.config.name,
                    "subjects": stream.config.subjects,
                    "messages": stream.state.messages,
                    "bytes": stream.state.bytes,
                    "consumer_count": stream.state.consumer_count,
                    "unprocessed_messages": unprocessed_messages,
                    "first_seq": stream.state.first_seq,
                    "last_seq": stream.state.last_seq,
                    "deleted_messages": stream.state.deleted,
                    "storage_type": stream.config.storage,
                    "retention_policy": stream.config.retention,
                    "max_age": stream.config.max_age
                }]
            else:
                # Get info for all streams
                streams = await js.streams_info()
                result = []
                for s in streams:
                    consumers = await js.consumers_info(s.config.name)
                    unprocessed_messages = sum(c.num_pending for c in consumers)
                    
                    result.append({
                        "stream": s.config.name,
                        "subjects": s.config.subjects,
                        "messages": s.state.messages,
                        "bytes": s.state.bytes,
                        "consumer_count": s.state.consumer_count,
                        "unprocessed_messages": unprocessed_messages,
                        "first_seq": s.state.first_seq,
                        "last_seq": s.state.last_seq,
                        "deleted_messages": s.state.deleted,
                        "storage_type": s.config.storage,
                        "retention_policy": s.config.retention,
                        "max_age": s.config.max_age
                    })
                return result
        except Exception as e:
            print(f"NATS connection error: {str(e)}")
            return []
        finally:
            try:
                await self.nc.close()
            except:
                pass

    def list_programs(self):
        """List all reconnaissance programs"""
        query = """
        SELECT p.name, 
               COUNT(DISTINCT d.id) as domains_count,
               COUNT(DISTINCT i.id) as ips_count,
               COUNT(DISTINCT u.id) as urls_count
        FROM programs p
        LEFT JOIN domains d ON p.id = d.program_id
        LEFT JOIN ips i ON p.id = i.program_id
        LEFT JOIN urls u ON p.id = u.program_id
        GROUP BY p.id, p.name
        ORDER BY p.name;
        """
        return self.execute_query(query)

    def get_interesting_endpoints(self, program_name: str = None):
        """Find potentially interesting endpoints based on various criteria"""
        if program_name:
            query = """
            SELECT 
                u.url, 
                httpx_data->>'title' as title,
                httpx_data->>'status_code' as status_code,
                httpx_data->>'tech' as technologies,
                p.name as program_name
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE httpx_data IS NOT NULL
            AND (
                httpx_data->>'status_code' IN ('200', '401', '403') 
                AND (
                    u.url ILIKE '%admin%' OR
                    u.url ILIKE '%api%' OR
                    u.url ILIKE '%jenkins%' OR
                    u.url ILIKE '%test%' OR
                    u.url ILIKE '%dev%' OR
                    u.url ILIKE '%stage%' OR
                    u.url ILIKE '%swagger%' OR
                    u.url ILIKE '%graphql%'
                )
            )
            AND p.name = $1
            """
            return self.execute_query(query, (program_name,))
        else:
            query = """
            SELECT 
                u.url, 
                httpx_data->>'title' as title,
                httpx_data->>'status_code' as status_code,
                httpx_data->>'tech' as technologies,
                p.name as program_name
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE httpx_data IS NOT NULL
            AND (
                httpx_data->>'status_code' IN ('200', '401', '403') 
                AND (
                    u.url ILIKE '%admin%' OR
                    u.url ILIKE '%api%' OR
                    u.url ILIKE '%jenkins%' OR
                    u.url ILIKE '%test%' OR
                    u.url ILIKE '%dev%' OR
                    u.url ILIKE '%stage%' OR
                    u.url ILIKE '%swagger%' OR
                    u.url ILIKE '%graphql%'
                )
            )
            """
            return self.execute_query(query)

    def get_technology_summary(self, program_name: str = None):
        """Summarize technologies used across endpoints"""
        if program_name:
            query = """
            WITH RECURSIVE tech_array AS (
                SELECT DISTINCT jsonb_array_elements_text(httpx_data->'tech') as tech
                FROM urls u
                JOIN programs p ON u.program_id = p.id
                WHERE httpx_data->'tech' IS NOT NULL
                AND p.name = $1
            )
            SELECT tech, COUNT(*) as count
            FROM tech_array
            GROUP BY tech
            ORDER BY count DESC;
            """
            return self.execute_query(query, (program_name,))
        else:
            query = """
            WITH RECURSIVE tech_array AS (
                SELECT DISTINCT jsonb_array_elements_text(httpx_data->'tech') as tech
                FROM urls u
                JOIN programs p ON u.program_id = p.id
                WHERE httpx_data->'tech' IS NOT NULL
            )
            SELECT tech, COUNT(*) as count
            FROM tech_array
            GROUP BY tech
            ORDER BY count DESC;
            """
            return self.execute_query(query)

    def get_recent_discoveries(self, days: int = 7, program_name: str = None):
        """Get recent discoveries across all assets"""
        if program_name:
            query = """
            SELECT 'domain' as type, domain as asset, discovered_at, p.name as program
            FROM domains d
            JOIN programs p ON d.program_id = p.id
            WHERE d.discovered_at >= NOW() - interval '$1 days'
            AND p.name = $2
            UNION ALL
            SELECT 'ip' as type, ip as asset, discovered_at, p.name as program
            FROM ips i
            JOIN programs p ON i.program_id = p.id
            WHERE i.discovered_at >= NOW() - interval '$1 days'
            AND p.name = $2
            UNION ALL
            SELECT 'url' as type, url as asset, discovered_at, p.name as program
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE u.discovered_at >= NOW() - interval '$1 days'
            AND p.name = $2
            ORDER BY discovered_at DESC;
            """
            return self.execute_query(query, (days, program_name))
        else:
            query = """
            SELECT 'domain' as type, domain as asset, discovered_at, p.name as program
            FROM domains d
            JOIN programs p ON d.program_id = p.id
            WHERE d.discovered_at >= NOW() - interval '$1 days'
            UNION ALL
            SELECT 'ip' as type, ip as asset, discovered_at, p.name as program
            FROM ips i
            JOIN programs p ON i.program_id = p.id
            WHERE i.discovered_at >= NOW() - interval '$1 days'
            UNION ALL
            SELECT 'url' as type, url as asset, discovered_at, p.name as program
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE u.discovered_at >= NOW() - interval '$1 days'
            ORDER BY discovered_at DESC;
            """
            return self.execute_query(query, (days,))

    def get_potential_vulnerabilities(self, program_name: str = None):
        """Find potential vulnerabilities based on technology and configuration"""
        if program_name:
            query = """
            SELECT url, 
                   httpx_data->>'title' as title,
                   httpx_data->>'tech' as technologies,
                   httpx_data->>'status_code' as status_code,
                   p.name as program_name
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE (
                httpx_data->>'tech' ILIKE '%WordPress%' OR
                httpx_data->>'tech' ILIKE '%PHP%' OR
                httpx_data->>'tech' ILIKE '%Jenkins%' OR
                httpx_data->>'server' ILIKE '%Apache%' OR
                httpx_data->>'tech' ILIKE '%Drupal%'
            )
            AND p.name = $1
            """
            return self.execute_query(query, (program_name,))
        else:
            query = """
            SELECT url, 
                   httpx_data->>'title' as title,
                   httpx_data->>'tech' as technologies,
                   httpx_data->>'status_code' as status_code,
                   p.name as program_name
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE (
                httpx_data->>'tech' ILIKE '%WordPress%' OR
                httpx_data->>'tech' ILIKE '%PHP%' OR
                httpx_data->>'tech' ILIKE '%Jenkins%' OR
                httpx_data->>'server' ILIKE '%Apache%' OR
                httpx_data->>'tech' ILIKE '%Drupal%'
            )
            """
            return self.execute_query(query)

    async def get_stream_messages(self, stream_name: str, subject: str = None, batch_size: int = 100):
        """Get messages from a specific NATS stream"""
        try:
            options = {
                "servers": ["nats://100.111.235.28:4222"],
                "connect_timeout": 5,
                "max_reconnect_attempts": 3
            }
            
            await self.nc.connect(**options)
            js = self.nc.jetstream()
            
            # Create a consumer with explicit configuration
            consumer_config = {
                "deliver_policy": "all",  # Get all messages
                "ack_policy": "explicit",
                "replay_policy": "instant",
                "inactive_threshold": 300000000000  # 5 minutes in nanoseconds
            }
            
            # If subject is provided, use it for subscription
            subscribe_subject = subject if subject else ">"
            
            consumer = await js.pull_subscribe(
                subscribe_subject,
                durable=None,
                stream=stream_name
            )
            
            messages = []
            try:
                # Fetch messages
                fetched = await consumer.fetch(batch_size)
                for msg in fetched:
                    # Get stream info for message counts
                    stream_info = await js.stream_info(stream_name)
                    
                    message_data = {
                        'subject': msg.subject,
                        'data': msg.data.decode() if msg.data else None,
                        'sequence': msg.metadata.sequence.stream if msg.metadata else None,
                        'time': msg.metadata.timestamp if msg.metadata else None,
                        'delivered_count': msg.metadata.num_delivered if msg.metadata else None,
                        'pending_count': msg.metadata.num_pending if msg.metadata else None,
                        'stream_total': stream_info.state.messages if stream_info.state else None,
                        'is_redelivered': msg.metadata.num_delivered > 1 if msg.metadata else False
                    }
                    messages.append(message_data)
                    
            except Exception as e:
                print(f"Error fetching messages: {str(e)}")
            
            return messages
            
        except Exception as e:
            print(f"NATS connection error: {str(e)}")
            return []
        finally:
            try:
                await self.nc.close()
            except:
                pass

    async def flush_stream(self, stream_name: str):
        """Flush all messages from a NATS stream
        Args:
            stream_name (str): Name of the stream to flush
        """
        try:
            options = {
                "servers": ["nats://100.111.235.28:4222"],
                "connect_timeout": 5,
                "max_reconnect_attempts": 3
            }
            
            await self.nc.connect(**options)
            js = self.nc.jetstream()
            
            try:
                # Purge all messages from the stream
                await js.purge_stream(stream_name)
                return {"status": "success", "message": f"Stream {stream_name} flushed successfully"}
            except Exception as e:
                return {"status": "error", "message": f"Error flushing stream: {str(e)}"}
            
        except Exception as e:
            return {"status": "error", "message": f"NATS connection error: {str(e)}"}
        finally:
            try:
                await self.nc.close()
            except:
                pass
    
    def list_program_domains(self, program_name: str) -> List[Dict[str, Any]]:
        """List all domains for a specific program.
        
        Args:
            program_name (str): Name of the program to query domains for
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing domain information
            
        Raises:
            DatabaseError: If the query fails to execute
            ProgramNotFoundError: If the program doesn't exist
        """
        query = """
            WITH program AS (
                SELECT id 
                FROM programs 
                WHERE name = %s
            )
            SELECT 
                d.domain,
                d.ips,
                d.discovered_at
            FROM domains d
            INNER JOIN program p ON d.program_id = p.id
        """
        
        return self.execute_query(query, (program_name,))


    def list_program_urls(self, program_name: str) -> List[Dict[str, Any]]:
        """List all URLs for a specific program"""
        query = """
        SELECT url, httpx_data, discovered_at
        FROM urls
        WHERE program_id = (SELECT id FROM programs WHERE name = $1);
        """
        return self.execute_query(query, (program_name,))

    def list_program_ips(self, program_name: str) -> List[Dict[str, Any]]:
        """List all IPs for a specific program"""
        query = """
            WITH program AS (
                SELECT id 
                FROM programs 
                WHERE name = %s
            )
            SELECT 
                i.ip,
                i.ptr
            FROM ips i
            INNER JOIN program p ON i.program_id = p.id
            WHERE program_id = program
        """
        return self.execute_query(query, (program_name,))

    def list_program_resolved_domains(self, program_name: str) -> List[Dict[str, Any]]:
        """List resolved domains with their individual IPs for a specific program.
        
        Args:
            program_name (str): Name of the program to query resolved domains for
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing domain information
                                with each IP address and its PTR record if available
            
        Raises:
            DatabaseError: If the query fails to execute
            ProgramNotFoundError: If the program doesn't exist
        """
        query = """
            WITH program AS (
                SELECT id 
                FROM programs 
                WHERE name = %s
            ),
            domain_ips AS (
                SELECT 
                    d.domain,
                    i.ip,
                    i.ptr
                FROM domains d
                INNER JOIN program p ON d.program_id = p.id
                CROSS JOIN UNNEST(d.ips) as ip_id
                INNER JOIN ips i ON i.id = ip_id
                WHERE d.ips IS NOT NULL 
                AND array_length(d.ips, 1) > 0
            )
            SELECT 
                domain,
                ip,
                ptr
            FROM domain_ips
            ORDER BY domain, ip;
        """
        
        return self.execute_query(query, (program_name,))


    def list_program_unresolved_domains(self, program_name: str) -> List[Dict[str, Any]]:
        """List unresolved domains for a specific program.
        
        Args:
            program_name (str): Name of the program to query unresolved domains for
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing domain information
                                for domains that have no IP resolutions
            
        Raises:
            DatabaseError: If the query fails to execute
            ProgramNotFoundError: If the program doesn't exist
        """
        query = """
            WITH program AS (
                SELECT id 
                FROM programs 
                WHERE name = %s
            )
            SELECT 
                d.domain,
                d.discovered_at,
                d.cnames,
                d.is_catchall
            FROM domains d
            INNER JOIN program p ON d.program_id = p.id
            WHERE (d.ips IS NULL 
            OR array_length(d.ips, 1) IS NULL 
            OR array_length(d.ips, 1) = 0)
            ORDER BY d.discovered_at DESC, d.domain;
        """
        
        return self.execute_query(query, (program_name,))

#################
async def async_main(args):
    client = H3XReconClient()
    
    try:
        result = None
        if args.command == 'list-programs':
            result = client.list_programs()
        elif args.command == 'interesting-endpoints':
            result = client.get_interesting_endpoints(args.program)
        elif args.command == 'tech-summary':
            result = client.get_technology_summary(args.program)
        elif args.command == 'recent-discoveries':
            result = client.get_recent_discoveries(args.days, args.program)
        elif args.command == 'potential-vulns':
            result = client.get_potential_vulnerabilities(args.program)
        elif args.command == 'stream-info':
            result = await client.get_stream_info(args.stream)
        elif args.command == 'stream-messages':
            result = await client.get_stream_messages(args.stream, args.subject, args.batch_size)
        elif args.command == 'flush-stream':
            result = await client.flush_stream(args.stream)
        elif args.command == 'send-job':
            await client.send_job(args.function_name, args.program, args.target, args.force)
            return
        elif args.command == 'list-domains':
            print(args.program)
            result = client.list_program_domains(args.program)
        elif args.command == 'list-urls':
            result = client.list_program_urls(args.program)
        elif args.command == 'list-ips':
            result = client.list_program_ips(args.program)
        elif args.command == 'list-resolved-domains':
            result = client.list_program_resolved_domains(args.program)
        elif args.command == 'list-unresolved-domains':
            result = client.list_program_unresolved_domains(args.program)
        if result:
            if args.output == 'json':
                print(json.dumps(result, indent=2, default=str))
            else:
                if isinstance(result, list) and result:
                    headers = result[0].keys()
                    rows = [x.values() for x in result]
                    print(tabulate(rows, headers=headers, tablefmt='grid'))
                elif isinstance(result, dict):
                    print(f"{result['status']}: {result['message']}")
                else:
                    print("No results found")
        else:
            print("No results found")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='H3XRecon Client Tool')
    parser.add_argument('--program', '-p', help='Specify program name')
    parser.add_argument('--command', '-c', required=True, choices=[
        'list-programs',
        'interesting-endpoints',
        'tech-summary',
        'recent-discoveries',
        'potential-vulns',
        'stream-info',
        'stream-messages',
        'flush-stream',
        'send-job',
        'list-domains',  # New command
        'list-urls',     # New command
        'list-ips',      # New command
        'list-resolved-domains',  # New command
        'list-unresolved-domains'  # New command
    ], help='Command to execute')
    parser.add_argument('--days', '-d', type=int, default=7, help='Number of days for recent discoveries')
    parser.add_argument('--output', '-o', choices=['table', 'json'], default='table', help='Output format')
    parser.add_argument('--stream', '-s', help='Specify NATS stream name')
    parser.add_argument('--subject', help='Specify NATS subject filter')
    parser.add_argument('--batch-size', type=int, default=100, help='Number of messages to fetch')
    parser.add_argument('--function-name', help='Function name for send-job command')
    parser.add_argument('--target', help='Target for send-job command')
    parser.add_argument('--force', type=bool, default=False, help='Force flag for send-job command')

    args = parser.parse_args()
    asyncio.run(async_main(args))

if __name__ == "__main__":
    main()
