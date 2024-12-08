from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import *
from h3xrecon.plugins.helper import send_url_data, send_domain_data, send_service_data
from loguru import logger
import asyncio
import json
import os

class TestHTTP(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {params.get("target", {})}")
        command = f"""
            #!/bin/bash
            httpx -u {params.get("target", {})} \
                -fr \
                -silent \
                -status-code \
                -content-length \
                -tech-detect \
                -threads 50 \
                -no-color \
                -json \
                -p 80-99,443-449,11443,8443-8449,9000-9003,8080-8089,8801-8810,3000,5000 \
                -efqdn \
                -tls-grab \
                -pa \
                -tls-probe \
                -pipeline \
                -http2 \
                -vhost \
                -bp \
                -ip \
                -cname \
                -asn \
                -random-agent
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            try:
                json_data = json.loads(output)
                yield json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        self.config = Config()
        self.db = db #DatabaseManager(self.config.database.to_dict())
        self.qm = QueueManager(self.config.nats)
        logger.debug(f"Incoming message:\nObject Type: {type(output_msg)}\nObject:\n{json.dumps(output_msg, indent=4)}")
        #if not await self.db.check_domain_regex_match(output_msg.get('source', {}).get('params', {}).get('target'), output_msg.get('program_id')):
        #    logger.info(f"Domain {output_msg.get('source', {}).get('params', {}).get('target')} is not part of program {output_msg.get('program_id')}. Skipping processing.")
        #else:
        url_msg = {
            "program_id": output_msg.get('program_id'),
            "data_type": "url",
            "data": [{
                "url": output_msg.get('output', {}).get('url'),
                "httpx_data": output_msg.get('output', {})
            }]
        }
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=url_msg)
        # await self.nc.publish(output_msg.get('recon_data_queue', "recon.data"), json.dumps(url_msg).encode())
        domains_to_add = (output_msg.get('output', {}).get('body_domains', []) + 
                            output_msg.get('output', {}).get('body_fqdn', []) + 
                            output_msg.get('output', {}).get('tls', {}).get('subject_an', []))
        logger.debug(domains_to_add)
        for domain in domains_to_add:
            if domain:
                await send_domain_data(data=domain, program_id=output_msg.get('program_id'))
        await send_service_data(data={
                "ip": output_msg.get('output').get('host'), 
                "port": int(output_msg.get('output').get('port')), 
                "protocol": "tcp"
        }, program_id=output_msg.get('program_id'))
