from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_ip_data, send_domain_data, parse_dns_record, send_dns_data, send_website_path_data
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url
from loguru import logger
import asyncio
import json
import os

class GauPlugin(ReconPlugin):
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
        command = f"echo {params.get("target", {})} | gau --subs"
        logger.debug(f"Running command: {command}")
        process = await self._create_subprocess_shell(command)
        
        async for output in self._read_subprocess_output(process):
            if output:
                yield {"url": output}

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        logger.debug(f"Processing output: {output_msg}")
        website_path_msg = {
            "path": output_msg.get('data', {}).get('url', ""),
        }
        await send_website_path_data(qm=qm, data=website_path_msg, program_id=output_msg.get('program_id'), execution_id=output_msg.get('execution_id'))
        domain_msg = {
            "domain": get_domain_from_url(output_msg.get('data', {}).get('url', ""))
        }
        await send_domain_data(qm=qm, data=domain_msg, program_id=output_msg.get('program_id'), execution_id=output_msg.get('execution_id'))
