from DatabaseManager import DatabaseManager
from QueueManager import QueueManager
from typing import Dict, Any, List, Callable
from loguru import logger
import json
import os
import traceback
import uuid
import redis
import asyncio

class JobProcessor:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.qm = QueueManager()
        self.worker_id = os.getenv('WORKER_ID', 'worker-1')
        self.redis_client = redis.Redis(host=os.getenv('H3XRECON_REDIS_SERVER', 'localhost'), port=os.getenv('H3XRECON_REDIS_PORT', '6379'), db=0)

    async def start(self):
        logger.info(f"Starting Job Processor (ID: {self.worker_id})...")
        
        await self.qm.connect()

        await self.qm.subscribe(
            subject="function.output",
            stream="FUNCTION_OUTPUT",
            durable_name="MY_CONSUMER",
            message_handler=self.message_handler,
            batch_size=1
        )

    async def stop(self):
        logger.info("Shutting down...")

    async def message_handler(self, msg):
        try:
            logger.debug(f"Incoming message:\nObject Type: {type(msg)}\nObject:\n{json.dumps(msg, indent=4)}")
            execution_id = msg['execution_id']
            timestamp = msg['timestamp']
            # Log or update function execution in database
            await self.log_or_update_function_execution(msg, execution_id, timestamp)
            
            function_name = msg.get("source", {}).get("function")
            if function_name:
                logger.info(f"Processing output from {function_name} on {msg.get('source', {}).get('target')}")
                logger.debug(msg)
                msg['in_scope'] = await self.db_manager.check_domain_regex_match(
                                                msg.get('source', {}).get('target'), 
                                                msg.get('program_id')
                                            )
                await self.process_function_output(msg)
            
        except Exception as e:
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            file_name = error_location.filename.split('/')[-1]
            line_number = error_location.lineno
            logger.error(f"Error in {file_name}:{line_number} - {type(e).__name__}: {str(e)}")
    
    async def log_or_update_function_execution(self, message_data: Dict[str, Any], execution_id: str, timestamp: str):
        try:
            log_entry = {
                "execution_id": execution_id,
                "timestamp": timestamp,
                "function_name": message_data.get("source", {}).get("function", "unknown"),
                "target": message_data.get("source", {}).get("target", "unknown"),
                "program_id": message_data.get("program_id"),
                "results": message_data.get("data", [])
            }
            if not message_data.get("nolog", False):
                await self.db_manager.log_or_update_function_execution(log_entry)

            # Update Redis with the last execution timestamp
            function_name = message_data.get("source", {}).get("function", "unknown")
            target = message_data.get("source", {}).get("target", "unknown")
            redis_key = f"{function_name}:{target}"
            self.redis_client.set(redis_key, timestamp)
        except Exception as e:
            logger.error(f"Error logging or updating function execution: {e}")

    async def process_function_output(self, msg_data: Dict[str, Any]):
        function_name = msg_data.get("source", {}).get("function")
        processor_name = f"process_{function_name}"
        processor = getattr(self, processor_name, None)
        if processor and callable(processor):
            await processor(msg_data)
        else:
            logger.warning(f"Unknown function: {function_name}")

    # async def process_function_output(self, msg_data: Dict[str, Any]):
    #     function_name = msg_data.get("source", {}).get("function")
    #     processor_name = f"process_{function_name}"
    #     processor = getattr(self, processor_name, None)
    #     if processor and callable(processor):
    #         await processor(msg_data)
    #     else:
    #         logger.warning(f"Unknown function: {function_name}")

    #############################################
    ## Recon tools output processing functions ##
    #############################################

    async def process_reverse_resolve_ip(self, msg_data: Dict[str, Any]):
        domain_msg = {
            "program_id": msg_data.get('program_id'),
            "data_type": "domain",
            "in_scope": msg_data.get('in_scope'),
            "data": [msg_data.get('output', []).get('domain')]
        }
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=domain_msg)
        ip_msg = {
            "program_id": msg_data.get('program_id'),
            "data_type": "ip",
            "in_scope": msg_data.get('in_scope'),
            "data": [msg_data.get('source', []).get('target')],
            "attributes": {
                "ptr": msg_data.get('output', {}).get('domain')
            }
        }
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=ip_msg)
    
    async def process_find_subdomains_subfinder(self, msg_data: Dict[str, Any]):
        domain_msg = {
            "program_id": msg_data.get('program_id'),
            "data_type": "domain",
            "in_scope": msg_data.get('in_scope'),
            "data": msg_data.get('output', {}).get('subdomain')
        }
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=domain_msg)
    
    async def process_find_subdomains_ctfr(self, msg_data: Dict[str, Any]):
        domain_msg = {
            "program_id": msg_data.get('program_id'),
            "data_type": "domain",
            "in_scope": msg_data.get('in_scope'),
            "data": msg_data.get('output', {}).get('subdomain')
        }
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=domain_msg)

    # Input format
    # {
    #     "program_id": 2,
    #     "source": {
    #         "function": "resolve_domain",
    #         "target": "target.com"
    #     },
    #     "data": {
    #         "host": "target.com",
    #         "a_records": ["1.1.1.1"],
    #         "cnames": []
    #     },
    #     "execution_id": "a73aee66-1594-44f1-af73-e91808797614",
    #     "timestamp": "2024-10-18T11:51:09.073035+00:00"
    # }
    async def process_resolve_domain(self, msg_data: Dict[str, Any]):
        try:
            logger.debug(msg_data)
            if await self.db_manager.check_domain_regex_match(msg_data.get('output').get('host'), msg_data.get('program_id')):
                if isinstance(msg_data.get('output').get('a_records'), list):
                    for ip in msg_data.get('output').get('a_records'):
                        if isinstance(ip, str):
                            try:
                                ip_message = {
                                    "program_id": msg_data.get('program_id'),
                                    "data_type": "ip",
                                    "data": [ip],
                                    "in_scope": msg_data.get('in_scope')
                                }
                                await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=ip_message)
                                logger.debug(f"Sent IP {ip} to data processor queue for domain {msg_data.get('source').get('target')}")
                            except Exception as e:
                                logger.error(f"Error processing IP {ip}: {str(e)}")
                        else:
                            logger.warning(f"Unexpected IP format: {ip}")
                else:
                    logger.warning(f"Unexpected IP format: {msg_data.get('output').get('a_records')}")
                #if msg_data.get('output', {}).get('cnames'):
                domain_message = {
                    "program_id": msg_data.get('program_id'),
                    "data_type": "domain",
                    "data": [msg_data.get('source', {}).get('target')],
                    "in_scope": msg_data.get('in_scope'),
                    "attributes": {"cnames": msg_data.get('output', {}).get('cnames'), "ips": msg_data.get('output', {}).get('a_records')}
                }
                await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=domain_message)
                logger.debug(f"Sent domain {msg_data.get('output').get('cnames')} to data processor queue for domain {msg_data.get('source').get('target')}")
            else:
                logger.info(f"Domain {msg_data.get('output').get('host')} is not part of program {msg_data.get('program_id')}. Skipping processing.")
        except Exception as e:
            logger.error(f"Error in process_resolved_domain: {str(e)}")
            logger.exception(e)

    # Input format
    # {
    #     "a": [
    #         "123.45.67.89"
    #     ],
    #     "body_domains": [
    #         "example1.com",
    #         "example2.com"
    #     ],
    #     "body_fqdn": [
    #         "subdomain1.example2.com",
    #         "subdomain2.example1.com"
    #     ],
    #     "body_preview": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    #     "cname": [
    #         "cdn1.example-cdn.net",
    #         "www.example2.com.cdn-provider.net"
    #     ],
    #     "content_length": 98765,
    #     "content_type": "text/html",
    #     "failed": false,
    #     "host": "123.45.67.89",
    #     "http2": true,
    #     "input": "www.example2.com",
    #     "knowledgebase": {
    #         "PageType": "other",
    #         "pHash": 0
    #     },
    #     "lines": 1234,
    #     "method": "GET",
    #     "path": "/",
    #     "port": "443",
    #     "resolvers": [
    #         "8.8.8.8:53",
    #         "8.8.4.4:53"
    #     ],
    #     "scheme": "https",
    #     "status_code": 200,
    #     "tech": [
    #         "Technology1",
    #         "Technology2",
    #         "Technology3"
    #     ],
    #     "time": "50.123456ms",
    #     "timestamp": "2024-01-01T12:00:00.123456789-05:00",
    #     "title": "Example Website Title",
    #     "tls": {
    #         "cipher": "TLS_EXAMPLE_CIPHER_256",
    #         "fingerprint_hash": {
    #         "md5": "0123456789abcdef0123456789abcdef",
    #         "sha1": "0123456789abcdef0123456789abcdef01234567",
    #         "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    #         },
    #         "host": "www.example2.com",
    #         "issuer_cn": "Example Certification Authority",
    #         "issuer_dn": "CN=Example Certification Authority, OU=Example Unit, O=Example Org, C=US",
    #         "issuer_org": [
    #         "Example Org"
    #         ],
    #         "not_after": "2026-01-01T12:00:00Z",
    #         "not_before": "2024-01-01T12:00:00Z",
    #         "port": "443",
    #         "probe_status": true,
    #         "serial": "01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF",
    #         "sni": "www.example2.com",
    #         "subject_an": [
    #             "example2.com",
    #             "www.example2.com"
    #         ],
    #         "subject_cn": "www.example2.com",
    #         "subject_dn": "CN=www.example2.com, O=Example Organization, L=Example City, ST=Example State, C=US",
    #         "subject_org": [
    #             "Example Organization"
    #         ],
    #         "tls_connection": "ctls",
    #         "tls_version": "tls13"
    #     },
    #     "url": "https://www.example2.com:443",
    #     "vhost": true,
    #     "words": 5678
    # }
    async def process_test_http(self, msg_data: Dict[str, Any]):
        logger.debug(f"Incoming message:\nObject Type: {type(msg_data)}\nObject:\n{json.dumps(msg_data, indent=4)}")
        if await self.db_manager.check_domain_regex_match(msg_data.get('source').get('target'), msg_data.get('program_id')):
            logger.info(f"Domain {msg_data.get('source').get('target')} is part of program {msg_data.get('program_id')}. Sending to data processor.")
            url_msg = {
                "program_id": msg_data.get('program_id'),
                "data_type": "url",
                "data": {
                    "url": msg_data.get('output', {}).get('url'),
                    "httpx_data": msg_data.get('output', {})
                }
            }
            await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=url_msg)
            # await self.nc.publish(msg_data.get('recon_data_queue', "recon.data"), json.dumps(url_msg).encode())
            domains_to_add = (msg_data.get('output', {}).get('body_domains', []) + 
                              msg_data.get('output', {}).get('body_fqdn', []) + 
                              msg_data.get('output', {}).get('tls', {}).get('subject_an', []))
            logger.debug(domains_to_add)
            for domain in domains_to_add:
                if domain:
                    domain_msg = {
                        "program_id": msg_data.get('program_id'),
                        "data_type": "domain",
                        "data": [domain]
                    }
                    await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=domain_msg)

            service_msg = {
                "program_id": msg_data.get('program_id'),
                "data_type": "service",
                "data": [{
                    "ip": msg_data.get('output').get('host'),
                    "port": int(msg_data.get('output').get('port')),
                    "protocol": "tcp",
                    "service": msg_data.get('output').get('scheme')
                }]
            }
            await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=service_msg)
    # Input format
    # {
    #     "program_id": 2,
    #     "source": {
    #         "function": "test_domain_catchall",
    #         "target": "target.com"
    #     },
    #     "output": {
    #         "domain": "target.com",
    #         "catchall": true
    #     },
    #     "execution_id": "a73aee66-1594-44f1-af73-e91808797614",
    #     "timestamp": "2024-10-18T11:51:09.073035+00:00"
    # }
    async def process_test_domain_catchall(self, msg_data: Dict[str, Any]):
        if await self.db_manager.check_domain_regex_match(msg_data.get('source').get('target'), msg_data.get('program_id')):
            logger.info(f"Domain {msg_data.get('source').get('target')} is part of program {msg_data.get('program_id')}. Sending to data processor.")
            msg = {
                "program_id": msg_data.get('program_id'),
                "data_type": "domain",
                "data": [msg_data.get('output', {}).get('domain')],
                "attributes": {
                    "is_catchall": msg_data.get('output', {}).get('is_catchall')
                }
            }
            await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)
            #await self.nc.publish("recon.data", json.dumps(msg).encode())
        else:
            logger.info(f"Domain {msg_data.get('source').get('target')} is not part of program {msg_data.get('program_id')}. Skipping processing.")

    # Input
    # {
    #     "program_id": 1,
    #     "execution_id": "49f9694f-287b-4e3b-a578-b1cacccb2023",
    #     "source": {
    #         "function": "port_scan",
    #         "target": "13.248.243.5"
    #     },
    #     "output": [{
    #         "ip": "13.248.243.5",
    #         "port": "443",
    #         "protocol": "tcp",
    #         "state": "open",
    #         "service": "https"
    #     }],
    #     "timestamp": "2024-10-29T15:49:07.273213+00:00"
    # }
    async def process_port_scan(self, msg_data: Dict[str, Any]):
        for service in msg_data.get('output', []):
            service_msg = {
                "program_id": msg_data.get('program_id'),
                "data_type": "service",
                "data": [{
                    "ip": service.get('ip'),
                    "port": int(service.get('port')),
                    "protocol": service.get('protocol')
                }]
            }
            await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=service_msg)