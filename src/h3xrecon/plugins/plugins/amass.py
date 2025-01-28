from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_domain_data, send_ip_data
from loguru import logger
import asyncio
import json
import os

class AmassPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["cidr"]
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 300

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        command = f"amass intel -active -cidr {params.get("target", {})} -ipv4"
        logger.debug(f"Running command: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            try:
                json_data = {
                    "domain": output.split(" ")[0],
                    "ip": output.split(" ")[1]
                }
                logger.debug(f"Output: {json_data}")
                yield json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        try:
            domain = output_msg.get('data').get('domain')
            ip = output_msg.get('data').get('ip')
            if isinstance(ip, str):
                try:
                    await send_ip_data(qm=qm, 
                                       data=ip, 
                                       program_id=output_msg.get('program_id'), 
                                       execution_id=output_msg.get('execution_id'), 
                                       trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
                    logger.debug(f"Sent IP {ip} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
                except Exception as e:
                    logger.error(f"Error processing IP {ip}: {str(e)}")
            else:
                logger.warning(f"Unexpected IP format: {ip}")
            await send_domain_data(qm=qm, 
                                   data=domain, 
                                   program_id=output_msg.get('program_id'), 
                                   execution_id=output_msg.get('execution_id'), 
                                   trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
            logger.debug(f"Sent domain {domain} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
        except Exception as e:
            logger.error(f"Error in process_resolved_domain: {str(e)}")
            logger.exception(e)