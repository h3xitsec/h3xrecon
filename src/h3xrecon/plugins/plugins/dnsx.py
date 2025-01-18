from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_ip_data, send_domain_data, parse_dns_record, send_dns_data
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url
from loguru import logger
import asyncio
import json
import os

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

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        command = f"echo {params.get("target", {})} | ~/.pdtm/go/bin/dnsx -nc -resp -recon -silent -j"
        logger.debug(f"Running command: {command}")
        process = await self._create_subprocess_shell(command)
        
        async for output in self._read_subprocess_output(process):
            try:
                json_data = json.loads(output)
                logger.debug(f"Parsed output: {json_data}")
                yield json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        try:
            # Process DNS entries
            for r in output_msg.get('output', {}).get('all', []):
                parsed_record = parse_dns_record(r)
                if parsed_record:
                    parsed_record['target_domain'] = output_msg.get('source', {}).get('params',{}).get('target')
                    await send_dns_data(qm=qm, 
                                        data=parsed_record,
                                        program_id=output_msg.get('program_id'),
                                        trigger_new_jobs=output_msg.get('trigger_new_jobs', False),
                                        execution_id=output_msg.get('execution_id')
                                    )
                    logger.debug(f"Sent DNS record {parsed_record} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
            for ip in output_msg.get('output', {}).get('a', []):
                if isinstance(ip, str):
                    try:
                        await send_ip_data(qm=qm, data=ip, program_id=output_msg.get('program_id'), trigger_new_jobs=output_msg.get('trigger_new_jobs', True), execution_id=output_msg.get('execution_id'))
                        logger.debug(f"Sent IP {ip} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
                    except Exception as e:
                        logger.error(f"Error processing IP {ip}: {str(e)}")
                else:
                    logger.warning(f"Unexpected IP format: {ip}")
            if output_msg.get('output', {}).get('ns'):
                for ns in output_msg.get('output', {}).get('ns', []):
                    try:
                        await send_domain_data(qm=qm, data=ns, program_id=output_msg.get('program_id'), trigger_new_jobs=output_msg.get('trigger_new_jobs', True), execution_id=output_msg.get('execution_id'))
                        logger.debug(f"Sent NS {ns} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
                    except Exception as e:
                        logger.error(f"Error processing NS {ns}: {str(e)}")
            #if output_msg.get('output', {}).get('cnames'):
            await send_domain_data(
                qm=qm,
                data=output_msg.get('source', {}).get('params', {}).get('target'),
                execution_id=output_msg.get('execution_id'),    
                program_id=output_msg.get('program_id'),
                attributes={"cnames": output_msg.get('output', {}).get('cnames'), "ips": output_msg.get('output', {}).get('a')},
                trigger_new_jobs=output_msg.get('trigger_new_jobs', True)
            )
            logger.debug(f"Sent domain {output_msg.get('source', {}).get('params', {}).get('target')} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
            #else:
            #    logger.info(f"Domain {output_msg.get('output').get('host')} is not part of program {output_msg.get('program_id')}. Skipping processing.")
        except Exception as e:
            logger.error(f"Error in process_resolved_domain: {str(e)}")
            logger.exception(e)