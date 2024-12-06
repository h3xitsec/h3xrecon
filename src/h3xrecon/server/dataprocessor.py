from h3xrecon.core import DatabaseManager
from h3xrecon.core import Config
from h3xrecon.core import QueueManager

import asyncio
from dataclasses import dataclass
from typing import Dict, Any, List, Callable
from loguru import logger
from urllib.parse import urlparse 
import os
import traceback
import json


@dataclass
class JobConfig:
    function: str
    param_map: Callable[[Any], Dict[str, Any]]

# Job mapping configuration
JOB_MAPPING: Dict[str, List[JobConfig]] = {
    "domain": [
        JobConfig(function="test_domain_catchall", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="resolve_domain", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="test_http", param_map=lambda result: {"target": result.lower()})
        # JobConfig(function="find_subdomains_subfinder", param_map=lambda result: {"target": result}),
        #JobConfig(function="find_subdomains_ctfr", param_map=lambda result: {"target": result})
    ],
    "ip": [
        JobConfig(function="reverse_resolve_ip", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="port_scan", param_map=lambda result: {"target": result.lower()})
    ]
}

class DataProcessor:
    def __init__(self, config: Config):
        self.qm = QueueManager(config.nats)
        self.db_manager = DatabaseManager() #config.database.to_dict())
        self.dataprocessor_id = f"dataprocessor-{os.getenv('HOSTNAME')}"
        self.data_type_processors = {
            "ip": self.process_ip,
            "domain": self.process_domain,
            "url": self.process_url,
            "service": self.process_service,
            "nuclei": self.process_nuclei
        }

    async def start(self):
        await self.qm.connect()
        await self.qm.subscribe(
            subject="recon.data",
            stream="RECON_DATA",
            durable_name="MY_CONSUMER",
            message_handler=self.message_handler,
            batch_size=1
        )
        logger.info(f"Starting data processor (Worker ID: {self.dataprocessor_id})...")


    async def stop(self):
        logger.info("Shutting down...")


    async def message_handler(self, msg):
        logger.debug(f"Incoming message:\nObject Type: {type(msg)}\nObject:\n{json.dumps(msg, indent=4)}")
        try:
            if isinstance(msg.get("data"), list):
                data_item = msg.get("data")[0]
            else:
                data_item = msg.get("data")
            if isinstance(data_item, dict) and data_item.get("data_type") == "url":
                data_item = data_item.get("data").get("url")
            processor = self.data_type_processors.get(msg.get("data_type"))
            if processor:
                await processor(msg)

        except Exception as e:
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            file_name = error_location.filename.split('/')[-1]
            line_number = error_location.lineno
            logger.error(f"Error in {file_name}:{line_number} - {type(e).__name__}: {str(e)}")
            logger.exception(e)
    
    async def trigger_new_jobs(self, program_id: int, data_type: str, result: Any):
        if os.getenv("H3XRECON_NO_NEW_JOBS", "false").lower() == "true":
            logger.info("H3XRECON_NO_NEW_JOBS is set. Skipping triggering new jobs.")
            return

        # Check if the data is in the program scope, if it is a domain
        if data_type == "domain":
            is_in_scope = await self.db_manager.check_domain_regex_match(result, program_id)
        else:
            is_in_scope = True
        if not is_in_scope:
            logger.info(f"Data {result} of type {data_type} is not in scope for program {program_id}. Skipping new jobs.")
            return

        if data_type in JOB_MAPPING:
            for job in JOB_MAPPING[data_type]:
                new_job = {
                    "function": job.function,
                    "program_id": program_id,
                    "params": job.param_map(result)
                }
                logger.info(f"Triggering {job.function} for {result}")
                await self.qm.publish_message(subject="function.execute", stream="FUNCTION_EXECUTE", message=new_job)

    ################################
    ## Data processing functions ##
    ################################

    async def process_ip(self, msg_data: Dict[str, Any]):
        for ip in msg_data.get('data'):
            ptr = msg_data.get('attributes', {}).get('ptr')
            if isinstance(ptr, list):
                ptr = ptr[0] if ptr else None  # Take the first PTR record if it's a list
            elif ptr == '':
                ptr = None  # Set empty string to None
            inserted = await self.db_manager.insert_ip(ip=ip, ptr=ptr, program_id=msg_data.get('program_id'))
            if inserted:
                await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="ip", result=ip)
    
    async def process_domain(self, msg_data: Dict[str, Any]):
        for domain in msg_data.get('data'):
            logger.info(f"Processing domain: {domain}")
            if not await self.db_manager.check_domain_regex_match(domain, msg_data.get('program_id')):
                logger.info(f"Domain {domain} is not part of program {msg_data.get('program_id')}. Skipping processing.")
                continue
            else:
                inserted = await self.db_manager.insert_domain(
                    domain=domain, 
                    ips=msg_data.get('attributes', {}).get('ips'), 
                    cnames=msg_data.get('attributes', {}).get('cnames'), 
                    is_catchall=msg_data.get('attributes', {}).get('is_catchall'), 
                    program_id=msg_data.get('program_id')
                )
            if inserted:
                logger.info(f"New domain inserted: {domain}")
                await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="domain", result=domain)
    
    async def process_url(self, msg: Dict[str, Any]):
        if msg:
            logger.info(msg)
            msg_data = msg.get('data', {})
            # Extract hostname from the URL
            for d in msg_data:
                try:
                    parsed_url = urlparse(d.get('url'))
                    hostname = parsed_url.hostname
                    if not hostname:
                        logger.error(f"Failed to extract hostname from URL: {d.get('url')}")
                        return
                    #program_name = await self.db_manager.get_program_name(msg.get('program_id'))
                    #logger.info(await self.db_manager.get_programs())
                    # Check if the hostname matches the scope regex
                    is_in_scope = await self.db_manager.check_domain_regex_match(hostname, msg.get('program_id'))
                    if not is_in_scope:
                        #logger.info(f"Hostname {hostname} is not in scope for program {program_name}. Skipping.")
                        return
                    logger.info(f"Processing URL result for program {msg.get('program_id')}: {d.get('url', {})}")
                    await self.db_manager.insert_url(
                        url=d.get('url'),
                        httpx_data=d.get('httpx_data', {}),
                        program_id=msg.get('program_id')
                    )
                    # Send a job to the workers to test the URL if httpx_data is missing
                    if not d.get('httpx_data'):
                        logger.info(f"Sending job to test URL: {d.get('url')}")
                        await self.qm.publish_message(subject="function.execute", stream="FUNCTION_EXECUTE", message={"function": "test_http", "program_id": msg.get('program_id'), "params": {"target": d.get('url')}})
            
                except Exception as e:
                    logger.error(f"Failed to process URL in program {msg.get('program_id')}: {e}")
                    logger.exception(e)
    
    async def process_nuclei(self, msg: Dict[str, Any]):
        if msg:
            logger.debug(f"Processing Nuclei result for program {msg.get('program_id')}: {msg}")
            msg_data = msg.get('data', {})
            for d in msg_data:
                try:
                    if d.get("type", "") == 'http':
                        parsed_url = urlparse(d.get('url', ""))
                        hostname = parsed_url.hostname
                    else:
                        hostname = d.get('url', "").split(":")[0]
                    if not hostname:
                        logger.error(f"Failed to extract hostname from URL: {d.get('output', {}).get('http', {}).get('url', {})}")
                        continue
                    else:
                        is_in_scope = await self.db_manager.check_domain_regex_match(hostname, msg.get('program_id'))
                        if is_in_scope:
                            logger.info(f"Processing Nuclei result for program {msg.get('program_id')}: {d.get('matched_at', {})}")
                            inserted = await self.db_manager.insert_nuclei(
                                program_id=msg.get('program_id'),
                                data=d
                            )
                            if inserted:
                                logger.info(f"New Nuclei result inserted: {d.get('matched_at', {})} | {d.get('template_id', {})} | {d.get('severity', {})}")
                        else:
                            logger.info(f"Hostname {hostname} is not in scope for program {msg.get('program_id')}. Skipping.")
                except Exception as e:
                    logger.error(f"Failed to process Nuclei result in program {msg.get('program_id')}: {e}")
                    logger.exception(e)

    async def process_service(self, msg_data: Dict[str, Any]):
        #logger.info(msg_data)
        if not isinstance(msg_data.get('data'), list):
            msg_data['data'] = [msg_data.get('data')]
        for i in msg_data.get('data'):
            inserted = await self.db_manager.insert_service(ip=i.get("ip"), port=i.get("port"), protocol=i.get("protocol"), program_id=msg_data.get('program_id'), service=i.get("service"))
            #if inserted:
            #    await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="ip", result=ip)

async def main():
    config = Config()
    config.setup_logging()
    data_processor = DataProcessor(config)
    await data_processor.start()
    
    try:
        # Keep the data processor running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await data_processor.stop()

def run():
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())