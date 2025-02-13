from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_ip_data, send_domain_data, parse_dns_record, send_dns_data, is_wildcard
from h3xrecon.core.utils import is_valid_hostname
from loguru import logger
import json
import os
import random

FILES_PATH = os.environ.get('H3XRECON_RECON_FILES_PATH')
RESOLVERS_FILE = f"{FILES_PATH}/resolvers-trusted.txt"

class DnsxPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 30

    @property
    def target_types(self) -> List[str]:
        return ["domain"]
    
    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_hostname(params.get("target", {}))

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        
        # Check if the target is a wildcard domain
        target = params.get("target", {})
        target_wildcard, target_wildcard_type = await is_wildcard(target)

        # Select 3 random resolvers from the file
        with open(RESOLVERS_FILE, 'r') as file:
            resolvers = file.read().splitlines()
        random_resolvers = random.sample(resolvers, 5)
        random_resolvers_str = ",".join(random_resolvers)
        
        # Run dnsx
        command = f"echo {target} | dnsx -nc -resp -recon -silent -j -r {random_resolvers_str}"
        logger.debug(f"Running command: {command}")
        stdout, stderr = self._create_subprocess_shell_sync(command)
        if stderr:
            logger.warning(f"dnsx stderr output: {stderr}")
        dnsx_results = stdout.splitlines()
        results = []
        for r in dnsx_results:
            try:
                json_data = json.loads(r)
                if json_data.get('status_code') == "NOERROR":
                    logger.debug(f"Parsed output: {json_data}")
                    results.append(json_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")
        
        if len(results) == 0:
            return
        
        # Yield the results along with the target and parent domain information
        message = {
            "dnsx_results": results,
            "target_wildcard": target_wildcard,
            "target": target
        }
        yield message

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        try:
            dnsx_results = output_msg.get('data', {}).get('dnsx_results', [])[0]
            # Process DNS entries
            for r in dnsx_results.get('all', []):
                parsed_record = parse_dns_record(r)
                if parsed_record:
                    parsed_record['target_domain'] = output_msg.get('source', {}).get('params',{}).get('target')
                    if parsed_record.get('target_domain') in parsed_record.get('hostname'):
                        await send_dns_data(qm=qm, 
                                            data=parsed_record,
                                            program_id=output_msg.get('program_id'),
                                            trigger_new_jobs=output_msg.get('trigger_new_jobs', False),
                                            execution_id=output_msg.get('execution_id'),
                                            response_id = None
                                        )
                        logger.debug(f"Sent DNS record {parsed_record} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
            
            # Process IPs from A records
            for ip in dnsx_results.get('a', []):
                if isinstance(ip, str):
                    try:
                        await send_ip_data(qm=qm, 
                                           data=ip, 
                                           program_id=output_msg.get('program_id'), 
                                           trigger_new_jobs=output_msg.get('trigger_new_jobs', True), 
                                           execution_id=output_msg.get('execution_id'), 
                                           response_id=None)
                        
                        logger.debug(f"Sent IP {ip} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
                    except Exception as e:
                        logger.error(f"Error processing IP {ip}: {str(e)}")
                else:
                    logger.warning(f"Unexpected IP format: {ip}")
            # Set the domain attributes
            dom_attr = {
                "cnames": dnsx_results.get('cnames', []), 
                "ips": dnsx_results.get('a', []), 
                "is_catchall": output_msg.get('data', {}).get('target_wildcard', False)
            }
            # Send the domain data to the data processor queue if there are any cnames or ips along with the catchall flag
            if (len(dom_attr.get("cnames")) + len(dom_attr.get("ips"))) > 0 or dom_attr.get("is_catchall"):
                await send_domain_data(
                    qm=qm,
                    data=output_msg.get('source', {}).get('params', {}).get('target'),
                    execution_id=output_msg.get('execution_id'),    
                    program_id=output_msg.get('program_id'),
                    attributes=dom_attr,
                    trigger_new_jobs=output_msg.get('trigger_new_jobs', True),
                    response_id=None
                )
                logger.debug(f"Sent domain {output_msg.get('source', {}).get('params', {}).get('target')} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")

            # Process NS records
            if dnsx_results.get('ns'):
                for ns in dnsx_results.get('ns', []):
                    try:
                        await send_domain_data(qm=qm,
                                               data=ns, 
                                               program_id=output_msg.get('program_id'), 
                                               trigger_new_jobs=output_msg.get('trigger_new_jobs', True), 
                                               execution_id=output_msg.get('execution_id'), 
                                               response_id=None)
                        logger.debug(f"Sent NS {ns} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
                    except Exception as e:
                        logger.error(f"Error processing NS {ns}: {str(e)}")
        except Exception as e:
            logger.error(f"Error in process_resolved_domain: {str(e)}")