#!/usr/bin/env python3

"""H3XRecon Client

Usage:
    client.py ( program ) ( add | del ) ( <program> )
    client.py [ -p <program> ] ( config ) ( add | del ) ( cidr | scope ) ( - | <item> )
    client.py [ -p <program> ] ( config ) ( list ) ( cidr | scope )
    client.py ( system ) ( queue ) ( show | messages | flush ) ( worker | job | data )
    client.py [ -p <program> ] ( list ) ( domains | ips ) [--resolved] [--unresolved]
    client.py [ -p <program> ] ( list ) ( urls | services ) [--details]
    client.py [ -p <program> ] ( add | del ) ( domain | ip | url ) ( - | <item> )
    client.py [ -p <program> ] ( sendjob ) ( <function> ) ( <target> ) [--force]

Options:
    -p --program     Program to work on.
    --resolved       Show only resolved items.
    --unresolved    Show only unresolved items.
    --force         Force execution of job.
    --details       Show details about URLs.
"""

import os
import sys
import re
import asyncio
import json
from urllib.parse import urlparse
from h3xrecon.core.database import DatabaseManager
from loguru import logger
from tabulate import tabulate
from h3xrecon.core.queue import QueueManager
from h3xrecon.core.config import Config
from docopt import docopt
from nats.aio.client import Client as NATS

VERSION = "0.0.1"

class H3XReconClient:
    arguments = None
    
    def __init__(self, arguments):
        self.config = Config()
        self.db = DatabaseManager(self.config.database.to_dict())
        print(self.config.database.to_dict())
        self.qm = QueueManager(self.config.nats)
        self.nc = NATS()
        self.nats_options = {
            "servers": [self.config.nats.url],
            "connect_timeout": 5,  # 5 seconds timeout
            "max_reconnect_attempts": 3
        }
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
            return await self.db.execute_query(query, program_name)
    
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


    async def get_stream_info(self, stream_name: str = None):
        """Get information about NATS streams"""
        try:

            
            await self.nc.connect(**self.nats_options)
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
    
    async def get_stream_messages(self, stream_name: str, subject: str = None, batch_size: int = 100):
        """Get messages from a specific NATS stream"""
        try:
            await self.nc.connect(**self.nats_options)
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
            await self.nc.connect(**self.nats_options)
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

        elif self.arguments.get('system'):
            if self.arguments.get('queue'):
                if self.arguments.get('show'):
                    if self.arguments['worker']:
                        result = await self.get_stream_info('FUNCTION_EXECUTE')
                    elif self.arguments['job']:
                        result = await self.get_stream_info('FUNCTION_OUTPUT')
                    elif self.arguments['data']:
                        result = await self.get_stream_info('RECON_DATA')
                    headers = result[0].keys()
                    rows = [x.values() for x in result]
                    print(tabulate(rows, headers=headers, tablefmt='grid'))

                elif self.arguments.get('messages'):
                    if self.arguments['worker']:
                        stream = 'FUNCTION_EXECUTE'
                    elif self.arguments['job']:
                        stream = 'FUNCTION_OUTPUT'
                    elif self.arguments['data']:
                        stream = 'RECON_DATA'
                    result = await self.get_stream_messages(stream)
                    headers = result[0].keys()
                    rows = [x.values() for x in result]
                    print(tabulate(rows, headers=headers, tablefmt='grid'))

                elif self.arguments.get('flush'):
                    result = await self.flush_stream(self.arguments['<queue_name>'])
                    print(result)

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
                if self.arguments.get('--details'):
                    result = await self.get_urls_details(self.arguments['<program>'])
                    headers = result[0].keys()
                    rows = [x.values() for x in result]
                    print(tabulate(rows, headers=headers, tablefmt='grid'))

                else:
                    result = await self.db.get_urls(self.arguments['<program>'])
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