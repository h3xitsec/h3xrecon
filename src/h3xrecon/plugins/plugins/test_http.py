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
            "-bp "
            "-ip "
            "-cname "
            "-asn "
            "-random-agent "
            "-favicon "
            "-hash sha256"
        )
        logger.debug(f"Command: {command}")
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
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.1)
                        if not line:
                            break
                            
                        try:
                            logger.debug(f"Line: {line.decode()}")
                            json_data = json.loads(line.decode())
                            yield json_data
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse JSON output: {e}")
                            
                    except asyncio.TimeoutError:
                        # Just continue the loop on timeout
                        continue
                        
            except Exception as e:
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
        website_msg = {
            "program_id": output_msg.get('program_id'),
            "data_type": "website",
            "data": [{
                "url": output_msg.get('output', {}).get('url'),
                "host": output_msg.get('output', {}).get('host'),
                "port": output_msg.get('output', {}).get('port'),
                "scheme": output_msg.get('output', {}).get('scheme'),
                "techs": output_msg.get('output', {}).get('tech', []),
                "favicon_hash": output_msg.get('output', {}).get('favicon', ""),
                "favicon_url": output_msg.get('output', {}).get('favicon_url', ""),
            }]
        }
        await qm.publish_message(subject="data.input", stream="DATA_INPUT", message=website_msg)
        website_path_msg = {
            "program_id": output_msg.get('program_id'),
            "data_type": "website_path",
            "data": [{
                "url": output_msg.get('output', {}).get('url'),
                "path": output_msg.get('output', {}).get('path'),
                "final_path": output_msg.get('output', {}).get('final_url'),
                "techs": output_msg.get('output', {}).get('tech', []),
                "response_time": output_msg.get('output', {}).get('response_time'),
                "lines": output_msg.get('output', {}).get('lines'),
                "title": output_msg.get('output', {}).get('title'),
                "words": output_msg.get('output', {}).get('words'),
                "method": output_msg.get('output', {}).get('method'),
                "scheme": output_msg.get('output', {}).get('scheme'),
                "status_code": output_msg.get('output', {}).get('status_code'),
                "content_type": output_msg.get('output', {}).get('content_type'),
                "content_length": output_msg.get('output', {}).get('content_length'),
                "chain_status_codes": output_msg.get('output', {}).get('chain_status_codes'),
                "page_type": output_msg.get('output', {}).get('page_type'),
                "body_preview": output_msg.get('output', {}).get('body_preview'),
                "resp_header_hash": output_msg.get('output', {}).get('hash', {}).get('header_sha256', ""),
                "resp_body_hash": output_msg.get('output', {}).get('hash', {}).get('body_sha256', ""),
            }]
        }
        await qm.publish_message(subject="data.input", stream="DATA_INPUT", message=website_path_msg)
        domains_to_add = (output_msg.get('output', {}).get('body_domains', []) + 
                            output_msg.get('output', {}).get('body_fqdn', []) + 
                            output_msg.get('output', {}).get('tls', {}).get('subject_an', []))
        logger.debug(f"Domains to add: {domains_to_add}")
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
