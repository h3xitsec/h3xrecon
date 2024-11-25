#!/usr/bin/env python3
from h3xrecon.__about__ import __version__ as VERSION
from h3xrecon.core import Config, DatabaseManager, QueueManager
import asyncio
import sys
import re
import yaml
from urllib.parse import urlparse
from loguru import logger
from tabulate import tabulate
from docopt import docopt
from nats.aio.client import Client as NATS

__doc__ = f"""h3xrecon client v{VERSION}

Usage:
    h3xrecon ( program ) ( list )
    h3xrecon ( program ) ( add | del) ( - | <program> )
    h3xrecon ( program ) ( import ) ( <file> )
    h3xrecon [ -p <program> ] ( config ) ( add | del ) ( cidr | scope ) ( - | <item> )
    h3xrecon [ -p <program> ] ( config ) ( list ) ( cidr | scope )
    h3xrecon [ -p <program> ] ( config ) ( database ) ( drop)
    h3xrecon ( system ) ( queue ) ( show | messages | flush ) ( worker | job | data )
    h3xrecon [ -p <program> ] ( list ) ( domains | ips ) [--resolved] [--unresolved]
    h3xrecon [ -p <program> ] ( list ) ( urls | services ) [--details]
    h3xrecon [ -p <program> ] ( add | del ) ( domain | ip | url ) ( - | <item> )
    h3xrecon [ -p <program> ] ( sendjob ) ( <function> ) ( <target> ) [--force]

Options:
    -p --program     Program to work on.
    --resolved       Show only resolved items.
    --unresolved    Show only unresolved items.
    --force         Force execution of job.
    --details       Show details about URLs.
"""

class Client:
    arguments = None
    
    def __init__(self, arguments):
        self.config = Config()
        if not self.config.client:
            logger.error("Failed to load client configuration")
            sys.exit(1)
        # Add console handler
        logger.remove()
        logger.add(
            sink=lambda msg: print(msg),
            level=self.config.logging.level,
            format=self.config.logging.format
        )
        # Add file handler if configured
        if self.config.logging.file_path:
            logger.add(
                sink=self.config.logging.file_path,
                level=self.config.logging.level,
                rotation="500 MB"
            )
        self.db = DatabaseManager(config=self.config.client.get('database').to_dict())
        self.qm = QueueManager(self.config.client.get('nats'))
        # Initialize arguments only if properly parsed by docopt
        if arguments:
            self.arguments = arguments
        else:
            raise ValueError("Invalid arguments provided.")
                    
    async def remove_program_config(self, program_name: str, config_type: str, items: list):
        """Remove scope or CIDR configuration from a program
        Args:
            program_name (str): Name of the program
            config_type (str): Type of config ('scope' or 'cidr')
            items (list): List of items to remove
        """
        program_id = await self.db.get_program_id(program_name)
        if not program_id:
            print(f"Error: Program '{program_name}' not found")
            return

        table_name = f"program_{config_type}"
        column_name = "pattern" if config_type == "scope" else "cidr"
        
        for item in items:
            query = f"""
            DELETE FROM {table_name}
            WHERE program_id = $1 AND {column_name} = $2
            """
            await self.db._write_records(query, program_id, item)
    
    async def send_job(self, function_name: str, program_name: str, target: str, force: bool):
        """Send a job to the worker using QueueManager"""
        try:
            program_id = await self.db.get_program_id(program_name)
        except Exception as e:
            logger.error(f"Non existent program '{program_name}'")
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

    async def get_urls_details(self, program_name: str = None):
        """Get details about URLs in a program"""
        if program_name:
            query = """
            SELECT 
                u.url, 
                httpx_data->>'title' as title,
                httpx_data->>'status_code' as status_code,
                httpx_data->>'tech' as technologies,
                httpx_data->>'body_preview' as body_preview,
                p.name as program_name
            FROM urls u
            JOIN programs p ON u.program_id = p.id
            WHERE p.name = $1
            """
            return await self.db._fetch_records(query, program_name)
    
    async def add_item(self, item_type: str, program_name: str, items: list):
        """Add items (domains, IPs, or URLs) to a program through the queue"""
        program_id = await self.db.get_program_id(program_name)
        if not program_id:
            print(f"Error: Program '{program_name}' not found")
            return

        # Format message based on item type
        if isinstance(items, str):
            items = [items]
        logger.debug(f"Adding {item_type} items to program {program_name}: {items}")
        if item_type == 'url':
            items = [{'url': item} for item in items]
        #for item in items:
        message = {
            "program_id": program_id,
            "data_type": item_type,
            "data": items
        }

        # For URLs, we need to format the data differently
        await self.qm.connect()
        await self.qm.publish_message(
            subject="recon.data",
            stream="RECON_DATA",
            message=message
        )
        await self.qm.close()

    async def remove_item(self, item_type: str, program_name: str, item: str) -> bool:
        """Remove an item (domain, IP, or URL) from a program"""
        program_id = await self.db.get_program_id(program_name)
        if not program_id:
            print(f"Error: Program '{program_name}' not found")
            return False

        message = {
            "program_id": program_id,
            "data_type": item_type,
            "action": "delete",
            "data": [item]
        }

        await self.qm.connect()
        await self.qm.publish_message(
            subject="recon.data",
            stream="RECON_DATA",
            message=message
        )
        await self.qm.close()
        return True
    
    async def drop_program_data(self, program_name: str):
        """Drop all data for a program"""
        await self.db.drop_program_data(program_name)
    
    async def import_programs(self, file_path: str):
        """Import programs from a JSON file"""
        with open(file_path, 'r') as file:
            data = yaml.safe_load(file)
            logger.debug(f"importing programs: {data}")
            for program in data['programs']:
                try:
                    print("Importing program: ", program.get('name'))
                    logger.debug(f"adding program: {program.get('name')}")
                    result = await self.db.add_program(program.get('name'))
                    if not result.success:
                        print(f"[-] Program '{program.get('name')}' already exists")
                    elif result.data:
                        print(f"[+] Program '{program.get('name')}' added successfully")
                    elif result.error:
                        print(f"[!] Error adding program: {result.error}")
                except Exception as e:
                    logger.error(f"Error adding program: {e}")
                if program.get('scope'):
                    for scope in program.get('scope'):
                        result = await self.db.add_program_scope(program.get('name'), scope)
                        if not result.success:
                            print(f"[-] Scope '{scope}' already exists in program '{program.get('name')}'")
                        elif result.data:
                            print(f"[+] Scope '{scope}' added successfully to program '{program.get('name')}'")
                        elif result.error:
                            print(f"[!] Error adding scope '{scope}' to program '{program.get('name')}': {result.error}")
                if program.get('cidr'):
                    for cidr in program.get('cidr'):
                        result = await self.db.add_program_cidr(program.get('name'), cidr)
                        if not result.success:
                            print(f"[-] CIDR '{cidr}' already exists in program '{program.get('name')}'")
                        elif result.data:
                            print(f"[+] CIDR '{cidr}' added successfully to program '{program.get('name')}'")
                        elif result.error:
                            print(f"[!] Error adding CIDR '{cidr}' to program '{program.get('name')}': {result.error}")
                print("")

        
    async def run(self):
        # h3xrecon program
        if self.arguments.get('program'):
            
            # h3xrecon program list
            if self.arguments.get('list'):
                #print(await self.db.get_programs())
                programs = await self.db.get_programs()
                [print(r.get("name")) for r in programs.data]
            
            # h3xrecon program add
            elif self.arguments.get('add'):
                result = await self.db.add_program(self.arguments['<program>'])
                logger.debug(f"db.add_programresult: {result}")
                if result.failed:
                    print(f"Error adding program: {result.error}")
                elif result.data == 0:
                    print(f"Program '{self.arguments['<program>']}' already exists")
                else:
                    print(f"Program '{self.arguments['<program>']}' added successfully")
            
            # h3xrecon program del
            elif self.arguments.get('del'):
                items = []
                if isinstance(self.arguments['<program>'], str):
                    items = [self.arguments['<program>']]
                if self.arguments.get('-'):
                    items.extend([u.rstrip() for u in process_stdin()])
                for i in items:
                    result = await self.db.remove_program(i)
                    if result.success:
                        print(f"Program '{i}' removed successfully")

            # h3xrecon program import
            elif self.arguments.get('import'):
                await self.import_programs(self.arguments['<file>']) 

        # h3xrecon -p program config
        elif self.arguments.get('config'):
        
            # h3xrecon -p program config add/del
            if self.arguments.get('add') or self.arguments.get('del'):
                if self.arguments.get('scope'): 
                    if self.arguments.get('-'):
                        for i in [u.rstrip() for u in process_stdin()]:
                            await self.db.add_program_scope(self.arguments['<program>'], i)
                    else:
                        await self.db.add_program_scope(self.arguments['<program>'], self.arguments['<item>'])
                elif self.arguments.get('cidr'):
                    if self.arguments.get('-'):
                        for i in [u.rstrip() for u in process_stdin()]:
                            await self.db.add_program_cidr(self.arguments['<program>'], i)
                    else:
                        await self.db.add_program_cidr(self.arguments['<program>'], self.arguments['<item>'])

            # h3xrecon -p program config list scope/cidr
            elif self.arguments.get('list'):
                if self.arguments.get('scope'):
                    scopes = await self.db.get_program_scope(self.arguments['<program>'])
                    [print(r.get('regex')) for r in scopes.data]
                elif self.arguments.get('cidr'):
                    cidrs = await self.db.get_program_cidr(self.arguments['<program>'])
                    [print(r.get('cidr')) for r in cidrs.data]
            
            # h3xrecon -p program config database drop
            elif self.arguments.get('database'):
                if self.arguments.get('drop'):
                    await self.db.drop_program_data(self.arguments['<program>'])
        
        # h3xrecon system
        elif self.arguments.get('system'):

            # h3xrecon system queue
            if self.arguments.get('queue'):
                if self.arguments['worker']:
                    stream = 'FUNCTION_EXECUTE'
                elif self.arguments['job']:
                    stream = 'FUNCTION_OUTPUT'
                elif self.arguments['data']:
                    stream = 'RECON_DATA'

                if self.arguments.get('show'):
                    result = await self.qm.get_stream_info(stream)
                    headers = result[0].keys()
                    rows = [x.values() for x in result]
                    print(tabulate(rows, headers=headers, tablefmt='grid'))

                elif self.arguments.get('messages'):
                    result = await self.qm.get_stream_messages(stream)
                    headers = result[0].keys()
                    rows = [x.values() for x in result]
                    print(tabulate(rows, headers=headers, tablefmt='grid'))

                elif self.arguments.get('flush'):
                    result = await self.qm.flush_stream(stream)
                    print(result)
        
        # h3xrecon -p program add domain/ip/url
        elif self.arguments.get('add'):
            if any(self.arguments.get(t) for t in ['domain', 'ip', 'url']):
                item_type = next(t for t in ['domain', 'ip', 'url'] if self.arguments.get(t))
                items = []
                if isinstance(self.arguments['<item>'], str):
                    items = [self.arguments['<item>']]
                if self.arguments.get('-'):
                    items.extend([u.rstrip() for u in process_stdin()])
                await self.add_item(item_type, self.arguments['<program>'], items)

        # h3xrecon -p program del domain/ip/url
        elif self.arguments.get('del'):
            if any(self.arguments.get(t) for t in ['domain', 'ip', 'url']):
                item_type = next(t for t in ['domain', 'ip', 'url'] if self.arguments.get(t))
                items = []
                if isinstance(self.arguments['<item>'], str):
                    items = [self.arguments['<item>']]
                if self.arguments.get('-'):
                    items.extend([u.rstrip() for u in process_stdin()])
                await self.remove_item(item_type, self.arguments['<program>'], items)

        # h3xrecon -p program list domains/ips/urls
        elif self.arguments.get('list'):          
            # h3xrecon -p program list domains
            if self.arguments.get('domains'):
                if self.arguments.get('--resolved'):
                    domains = await self.db.get_resolved_domains(self.arguments['<program>'])
                    [print(f"{r['domain']} -> {r['resolved_ips']}") for r in domains.data]
                elif self.arguments.get('--unresolved'):
                    domains = await self.db.get_unresolved_domains(self.arguments['<program>'])
                    [print(r['domain']) for r in domains.data]
                else:
                    domains = await self.db.get_domains(self.arguments['<program>'])
                    [print(r['domain']) for r in domains.data]

            # h3xrecon -p program list ips
            elif self.arguments.get('ips'):
                if self.arguments.get('--resolved'):
                    ips = await self.db.get_reverse_resolved_ips(self.arguments['<program>'])
                    [print(f"{r['ip']} -> {r['ptr']}") for r in ips.data]
                elif self.arguments.get('--unresolved'):
                    ips = await self.db.get_not_reverse_resolved_ips(self.arguments['<program>'])
                    [print(r['ip']) for r in ips.data]
                else:
                    ips = await self.db.get_ips(self.arguments['<program>'])
                    [print(r['ip']) for r in ips.data]

            # h3xrecon -p program list urls
            elif self.arguments.get('urls'):
                if self.arguments.get('--details'):
                    result = await self.get_urls_details(self.arguments['<program>'])
                    headers = result[0].keys()
                    rows = [x.values() for x in result]
                    print(tabulate(rows, headers=headers, tablefmt='grid'))

                else:
                    urls = await self.db.get_urls(self.arguments['<program>'])
                    [print(r['url']) for r in urls.data]
                
            # h3xrecon -p program list services
            elif self.arguments.get('services'):
                services = await self.db.get_services(self.arguments['<program>'])
                [print(f"{r.get('protocol')}:{r.get('ip')}:{r.get('port')}") for r in services.data]

        # h3xrecon -p program sendjob
        elif self.arguments.get('sendjob'):
            await self.send_job(
                function_name=self.arguments['<function>'],
                program_name=self.arguments['<program>'],
                target=self.arguments['<target>'],
                force=self.arguments['--force']
            )

        else:
            raise ValueError("No valid argument found")

def process_stdin():
    # Process standard input and filter out empty lines
    return list(filter(lambda x: not re.match(r'^\s*$', x),  sys.stdin.read().split('\n')))

def main():
    try:
        # Parse arguments
        if len(sys.argv) == 1: # i.e just the program name
            sys.argv.append('-h')
        arguments = docopt(__doc__, argv=sys.argv[1:], version=VERSION)
        # Pass parsed arguments to Client
        client = Client(arguments)
        asyncio.run(client.run())
    except Exception as e:
        print('[ERROR] ' + str(e))

if __name__ == '__main__':
    main()