#!/usr/bin/python3

"""H3XRecon Client

Usage:
    client.py ( program ) ( add | del ) ( <program> )
    client.py [ -p <program> ] ( config ) ( add | del ) ( cidr | scope ) ( - | <item> )
    client.py [ -p <program> ] ( config ) ( list ) ( cidr | scope )
    client.py [ -p <program> ] ( list ) ( domains | ips ) [--resolved] [--unresolved]
    client.py [ -p <program> ] ( list ) ( urls | services )
    client.py [ -p <program> ] ( add | del ) ( domain | ip | url ) ( - | <item> )
    client.py [ -p <program> ] ( sendjob ) ( <function> ) ( <target> ) [--force]

Options:
    -p --program     Program to work on.
    --resolved       Show only resolved items.
    --unresolved    Show only unresolved items.
    --force         Force execution of job.
"""

import os
import sys
import json
import re
import asyncio
from urllib.parse import urlparse
from DatabaseManager import DatabaseManager
from QueueManager import QueueManager
from docopt import docopt

VERSION = "0.0.1"

class H3XReconClient:
    arguments = None
    
    def __init__(self, arguments):
        self.db = DatabaseManager()
        self.qm = QueueManager()
        # Initialize arguments only if properly parsed by docopt
        if arguments:
            self.arguments = arguments
        else:
            raise ValueError("Invalid arguments provided.")

    async def send_job(self, function_name: str, program_name: str, target: str, force: bool):
        """Send a job to the worker using QueueManager"""
        program_id = await self.db.get_program_id(program_name)
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
    
    async def add_item(self, item_type: str, program_name: str, items: list):
        """Add items (domains, IPs, or URLs) to a program through the queue"""
        program_id = await self.db.get_program_id(program_name)
        if not program_id:
            print(f"Error: Program '{program_name}' not found")
            return

        # Format message based on item type
        if isinstance(items, str):
            items = [items]

        for item in items:
            message = {
                "program_id": program_id,
                "data_type": item_type,
                "data": {
                    "url": item
                }
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

    async def run(self):
        #import pprint
        #pp = pprint.PrettyPrinter(indent=4)
        #pp.pprint(self.arguments)
        # Execute based on parsed arguments
        if self.arguments.get('program'):
            if self.arguments.get('add'):
                await self.db.add_program(self.arguments['<program>'])
            elif self.arguments.get('del'):
                if await self.db.remove_program(self.arguments['<program>']):
                    print(f"Program '{self.arguments['<program>']}' removed successfully")
                else:
                    print(f"Failed to remove program '{self.arguments['<program>']}'")

        elif self.arguments.get('config'):
            if self.arguments.get('list'):
                if self.arguments.get('scope'):
                    [print(r) for r in await self.db.get_program_scope(self.arguments['<program>'])]
                elif self.arguments.get('cidr'):
                    [print(r) for r in await self.db.get_program_cidr(self.arguments['<program>'])]

        elif self.arguments.get('add'):
            if any(self.arguments.get(t) for t in ['domain', 'ip', 'url']):
                item_type = next(t for t in ['domain', 'ip', 'url'] if self.arguments.get(t))
                items = []
                if isinstance(self.arguments['<item>'], str):
                    items = [self.arguments['<item>']]
                if self.arguments.get('-'):
                    items.extend([u.rstrip() for u in process_stdin()])
                await self.add_item(item_type, self.arguments['<program>'], items)

        elif self.arguments.get('del'):
            if any(self.arguments.get(t) for t in ['domain', 'ip', 'url']):
                item_type = next(t for t in ['domain', 'ip', 'url'] if self.arguments.get(t))
                if isinstance(self.arguments['<item>'], str):
                    if await self.remove_item(item_type, self.arguments['<program>'], self.arguments['<item>']):
                        print(f"{item_type.capitalize()} '{self.arguments['<item>']}' removed from program '{self.arguments['<program>']}'")
                    else:
                        print(f"Failed to remove {item_type} '{self.arguments['<item>']}' from program '{self.arguments['<program>']}'")
                if self.arguments.get('-'):
                    for i in [u.rstrip() for u in process_stdin()]:
                        await self.remove_item(item_type, self.arguments['<program>'], i)

        elif self.arguments.get('list'):                
            if self.arguments.get('domains'):
                if self.arguments.get('--resolved'):
                    [print(f"{r['domain']} -> {r['resolved_ips']}") for r in await self.db.get_resolved_domains(self.arguments['<program>'])]
                elif self.arguments.get('--unresolved'):
                    [print(r['domain']) for r in await self.db.get_unresolved_domains(self.arguments['<program>'])]
                else:
                    [print(r['domain']) for r in await self.db.get_domains(self.arguments['<program>'])]

            elif self.arguments.get('ips'):
                if self.arguments.get('--resolved'):
                    [print(f"{r['ip']} -> {r['ptr']}") for r in await self.db.get_reverse_resolved_ips(self.arguments['<program>'])]
                elif self.arguments.get('--unresolved'):
                    [print(r['ip']) for r in await self.db.get_not_reverse_resolved_ips(self.arguments['<program>'])]
                else:
                    [print(r['ip']) for r in await self.db.get_ips(self.arguments['<program>'])]

            elif self.arguments.get('urls'):
                [print(r['url']) for r in await self.db.get_urls(self.arguments['<program>'])]
            
            elif self.arguments.get('services'):
                [print(f"{r.get('protocol')}:{r.get('ip')}:{r.get('port')}") for r in await self.db.get_services(self.arguments['<program>'])]

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
        arguments = docopt(__doc__, argv=sys.argv[1:], version=VERSION)
        # Pass parsed arguments to H3XReconClient
        client = H3XReconClient(arguments)
        asyncio.run(client.run())
    except Exception as e:
        print('[ERROR] ' + str(e))
            
if __name__ == '__main__':
    main()
