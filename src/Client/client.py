#!/usr/bin/python3

"""H3XRecon Client

Usage:
    client.py ( add | remove ) ( program ) ( <program> )
    client.py ( list ) ( program | domains | ips | urls | services )
    client.py [-p <program>] ( add ) ( cidr | scope ) ( - | <item> )
    client.py [-p <program>] ( list ) ( domains | ips | urls | services | cidr | scope )
    client.py [-p <program>] ( sendjob ) ( <function> ) ( <target> ) [--force]

Options:
    -p --program     Program to work on.
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

    async def run(self):
        #import pprint
        #pp = pprint.PrettyPrinter(indent=4)
        #pp.pprint(self.arguments)
        # Execute based on parsed arguments
        if self.arguments.get('list'):
            if self.arguments.get('domains'):
                if self.arguments['<program>']:   
                    [print(r['domain']) for r in await self.db.get_domains(self.arguments['<program>'])]
                else:
                    [print(r['domain']) for r in await self.db.get_domains()]

            elif self.arguments.get('ips'):
                if self.arguments['<program>']:   
                    [print(r['ip']) for r in await self.db.get_ips(self.arguments['<program>'])]
                else:
                    [print(r['ip']) for r in await self.db.get_ips()]

            elif self.arguments.get('urls'):
                if self.arguments['<program>']:   
                    [print(r['url']) for r in await self.db.get_urls(self.arguments['<program>'])]
                else:
                    [print(r['url']) for r in await self.db.get_urls()]
            
            elif self.arguments.get('services'):
                if self.arguments['<program>']:   
                    [print(f"{r.get('protocol')}:{r.get('ip')}:{r.get('port')}") for r in await self.db.get_services(self.arguments['<program>'])]
                else:
                    [print(f"{r.get('protocol')}:{r.get('ip')}:{r.get('port')}") for r in await self.db.get_services()]

            elif self.arguments.get('scope'):
                [print(r) for r in await self.db.get_program_scope(self.arguments['<program>'])]

            elif self.arguments.get('cidr'):
                [print(r) for r in await self.db.get_program_cidr(self.arguments['<program>'])]

            elif self.arguments.get('program'):
                [print(r['name']) for r in await self.db.get_programs()]


        elif self.arguments.get('add'):
            if self.arguments.get('cidr'):
                if isinstance(self.arguments['<item>'], str):
                    await self.db.add_program_cidr(self.arguments['<program>'], self.arguments['<item>'])
                if self.arguments.get('-'):
                    for i in [u.rstrip() for u in process_stdin()]:
                        await self.db.add_program_cidr(self.arguments['<program>'], i)
            
            elif self.arguments.get('scope'):
                if isinstance(self.arguments['<item>'], str):
                    await self.db.add_program_scope(self.arguments['<program>'], self.arguments['<item>'])
                if self.arguments.get('-'):
                    for i in [u.rstrip() for u in process_stdin()]:
                        await self.db.add_program_scope(self.arguments['<program>'], i)
        
            elif self.arguments.get('program'):
                await self.db.add_program(self.arguments['<program>'])

        elif self.arguments.get('sendjob')  :
            await self.send_job(function_name=self.arguments['<function>'], program_name=self.arguments['<program>'], target=self.arguments['<target>'], force=self.arguments['--force'])
        
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
