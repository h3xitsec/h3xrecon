from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_domain_data, send_service_data, send_certificate_data, send_website_data, send_website_path_data
from h3xrecon.core.utils import parse_url, is_valid_hostname
from loguru import logger
import asyncio
import json
import os
import urllib.parse

class TestHTTP(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["domain", "url"]


    @property
    def timeout(self) -> int:
        return 300  # 5 minutes timeout

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get('target', {})}")
        command = (
            f"httpx -u {params.get('target', {})} "
            "-fr "
            "-silent "
            "-status-code "
            "-content-length "
            "-tech-detect "
            "-threads 50 "
            "-no-color "
            "-json "
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
        if self.get_target_type(params.get('target', {})) == "domain":
            command += " -p 80-99,443-449,11443,8443-8449,9000-9003,8080-8089,8801-8810,3000,5000 "
        logger.debug(f"Command: {command}")
        process = None
        try:
            process = await self._create_subprocess_shell(command)
            
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
        # Parse full URL to extract host, port and path
        if output_msg.get("data", None):
            logger.debug(f"Parsing URL: {output_msg.get("data", {}).get('url', '')}")
            parsed_website_and_path = parse_url(output_msg.get("data", {}).get('url', ""))
            if not parsed_website_and_path:
                logger.error(f"Error parsing URL: {output_msg.get("data", {}).get('url', '')}")
                return
            website_msg = parsed_website_and_path.get('website')
            website_msg['techs'] = output_msg.get("data", {}).get('tech', [])
            website_msg['favicon_hash'] = output_msg.get("data", {}).get('favicon', "")
            website_msg['favicon_url'] = output_msg.get("data", {}).get('favicon_url', "")
            await send_website_data(qm=qm, 
                                    data=website_msg, 
                                    program_id=output_msg.get('program_id', ""),
                                    execution_id=output_msg.get('execution_id', ""),
                                    trigger_new_jobs=output_msg.get('trigger_new_jobs', True))

            # Send website path data with full URL
            website_path_msg = parsed_website_and_path.get('website_path')
            website_path_msg['techs'] = output_msg.get("data", {}).get('tech', [])
            website_path_msg['response_time'] = output_msg.get("data", {}).get('response_time')
            website_path_msg['lines'] = output_msg.get("data", {}).get('lines')
            website_path_msg['title'] = output_msg.get("data", {}).get('title')
            website_path_msg['words'] = output_msg.get("data", {}).get('words')
            website_path_msg['method'] = output_msg.get("data", {}).get('method')
            website_path_msg['status_code'] = output_msg.get("data", {}).get('status_code')
            website_path_msg['content_type'] = output_msg.get("data", {}).get('content_type')
            website_path_msg['content_length'] = output_msg.get("data", {}).get('content_length')
            website_path_msg['chain_status_codes'] = output_msg.get("data", {}).get('chain_status_codes')
            website_path_msg['page_type'] = output_msg.get("data", {}).get('page_type')
            website_path_msg['body_preview'] = output_msg.get("data", {}).get('body_preview')
            website_path_msg['resp_header_hash'] = output_msg.get("data", {}).get('hash', {}).get('header_sha256', "")
            website_path_msg['resp_body_hash'] = output_msg.get("data", {}).get('hash', {}).get('body_sha256', "")
            await send_website_path_data(qm=qm, 
                                         data=website_path_msg, 
                                         program_id=output_msg.get('program_id', ""),
                                         trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
            # Extract domain names from the httpx output to send to data worker
            # All domains specified in response body, all FQDNs and all subject alternative names
            domains_to_add = (output_msg.get("data", {}).get('body_domains', []) + 
                                output_msg.get("data", {}).get('body_fqdn', []) + 
                                output_msg.get("data", {}).get('tls', {}).get('subject_an', []))
            
            logger.debug(f"Domains to add: {domains_to_add}")
            if len(domains_to_add) > 0:
                for domain in domains_to_add:
                    if is_valid_hostname(domain):
                        logger.debug(f"Sending domain data for {domain}")
                        await send_domain_data(qm=qm, 
                                               data=domain, 
                                               program_id=output_msg.get('program_id'), 
                                               execution_id=output_msg.get('execution_id', ""), 
                                               trigger_new_jobs=output_msg.get('trigger_new_jobs', True))

            # Parse and send service data
            await send_service_data(qm=qm, data={
                    "ip": output_msg.get("data").get('host'), 
                    "port": int(output_msg.get("data").get('port')), 
                    "protocol": "tcp",
                    "scheme": output_msg.get("data").get('scheme', ""),
                    "trigger_new_jobs": output_msg.get('trigger_new_jobs', True)
                }, program_id=output_msg.get('program_id'))

            # If a HTTPS response is parsed, send certificate data
            if output_msg.get("data").get('tls', {}).get('subject_dn', "") != "":
                await send_certificate_data(qm=qm,
                                            data={
                                                "url": output_msg.get("data", {}).get('url', ""),
                                                "cert": {   
                                                    "subject_dn": output_msg.get("data").get('tls', {}).get('subject_dn', ""),
                                                    "subject_cn": output_msg.get("data").get('tls', {}).get('subject_cn', ""),
                                                    "subject_an": output_msg.get("data").get('tls', {}).get('subject_an', ""),
                                                    "valid_date": output_msg.get("data").get('tls', {}).get('not_before', ""),
                                                    "expiry_date": output_msg.get("data").get('tls', {}).get('not_after', ""),
                                                    "issuer_dn": output_msg.get("data").get('tls', {}).get('issuer_dn', ""),
                                                    "issuer_cn": output_msg.get("data").get('tls', {}).get('issuer_cn', ""),
                                                    "issuer_org": output_msg.get("data").get('tls', {}).get('issuer_org', ""),
                                                    "serial": output_msg.get("data").get('tls', {}).get('serial', ""),
                                                    "fingerprint_hash": output_msg.get("data").get('tls', {}).get('fingerprint_hash', {}).get('sha256', "")
                                                }
                                            }, 
                                            program_id=output_msg.get('program_id'),
                                            execution_id=output_msg.get('execution_id', ""),
                                            trigger_new_jobs=output_msg.get('trigger_new_jobs', True))