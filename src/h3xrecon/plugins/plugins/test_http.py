from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_domain_data, send_service_data, send_certificate_data
from loguru import logger
import asyncio
import json
import os

class TestHTTP(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    @property
    def timeout(self) -> int:
        return 300  # 5 minutes timeout

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get('target', {})}")
        command = (
            f"~/.pdtm/go/bin/httpx -u {params.get('target', {})} "
            "-fr "
            "-silent "
            "-status-code "
            "-content-length "
            "-tech-detect "
            "-threads 50 "
            "-no-color "
            "-json "
            "-p 80-99,443-449,11443,8443-8449,9000-9003,8080-8089,8801-8810,3000,5000 "
            "-efqdn "
            "-tls-grab "
            "-pa "
            "-tls-probe "
            "-pipeline "
            "-http2 "
            "-vhost "
            "-bp "
            "-ip "
            "-cname "
            "-asn "
            "-random-agent"
        )
        
        process = None
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            
            try:
                while True:
                    try:
                        # Check if the task is being cancelled
                        if asyncio.current_task().cancelled():
                            logger.info(f"Task cancelled, terminating {self.name}")
                            if process:
                                process.terminate()  # Send SIGTERM first
                                try:
                                    await asyncio.wait_for(process.wait(), timeout=5.0)
                                except asyncio.TimeoutError:
                                    process.kill()  # If it doesn't terminate, force kill
                            return
                            
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.1)
                        if not line:
                            break
                            
                        try:
                            json_data = json.loads(line.decode())
                            yield json_data
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse JSON output: {e}")
                            
                    except asyncio.TimeoutError:
                        # Just continue the loop on timeout
                        continue
                        
            except asyncio.CancelledError:
                logger.info(f"Task cancelled, terminating {self.name}")
                if process:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                raise
                
            await process.wait()
                
        except Exception as e:
            logger.error(f"Error during HTTP test: {str(e)}")
            if process:
                process.kill()
            raise
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        logger.debug(f"Incoming message:\nObject Type: {type(output_msg)} : {json.dumps(output_msg)}")
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
        await qm.publish_message(subject="recon.data", stream="RECON_DATA", message=url_msg)
        # await self.nc.publish(output_msg.get('recon_data_queue', "recon.data"), json.dumps(url_msg).encode())
        domains_to_add = (output_msg.get('output', {}).get('body_domains', []) + 
                            output_msg.get('output', {}).get('body_fqdn', []) + 
                            output_msg.get('output', {}).get('tls', {}).get('subject_an', []))
        logger.debug(domains_to_add)
        if len(domains_to_add) > 0:
            for domain in domains_to_add:
                logger.debug(f"Sending domain data for {domain}")
                await send_domain_data(qm=qm, data=domain, program_id=output_msg.get('program_id'))

        await send_service_data(qm=qm, data={
                "ip": output_msg.get('output').get('host'), 
                "port": int(output_msg.get('output').get('port')), 
                "protocol": "tcp",
                "scheme": output_msg.get('output').get('scheme', "")
            }, program_id=output_msg.get('program_id'))

        if output_msg.get('output').get('tls', {}).get('subject_dn', "") != "":
            await send_certificate_data(qm=qm,data={
                "url": output_msg.get('output', {}).get('url', ""),
                "cert": {   
                    "subject_dn": output_msg.get('output').get('tls', {}).get('subject_dn', ""),
                    "subject_cn": output_msg.get('output').get('tls', {}).get('subject_cn', ""),
                    "subject_an": output_msg.get('output').get('tls', {}).get('subject_an', ""),
                    "valid_date": output_msg.get('output').get('tls', {}).get('not_before', ""),
                    "expiry_date": output_msg.get('output').get('tls', {}).get('not_after', ""),
                    "issuer_dn": output_msg.get('output').get('tls', {}).get('issuer_dn', ""),
                    "issuer_cn": output_msg.get('output').get('tls', {}).get('issuer_cn', ""),
                    "issuer_org": output_msg.get('output').get('tls', {}).get('issuer_org', ""),
                    "serial": output_msg.get('output').get('tls', {}).get('serial', ""),
                    "fingerprint_hash": output_msg.get('output').get('tls', {}).get('fingerprint_hash', {}).get('sha256', "")
                }
            }, program_id=output_msg.get('program_id'))
