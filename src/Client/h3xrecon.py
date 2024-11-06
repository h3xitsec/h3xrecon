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
