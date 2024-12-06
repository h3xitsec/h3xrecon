from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import *
from h3xrecon.plugins.helper import send_ip_data, send_domain_data
from loguru import logger
import asyncio
import os

class ReverseResolveIP(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {params.get("target", {})}")
        command = f"""
            echo "{params.get("target", {})}" | dnsx -silent -nc -ptr -resp -j|jq -cr '.ptr[]'
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            yield {"domain": output.strip().strip('"')}

        await process.wait()
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        self.config = Config()
        await send_domain_data(data=output_msg.get('output', []).get('domain'), program_id=output_msg.get('program_id'))
        await send_ip_data(data=output_msg.get('source', []).get('params', {}).get('target'), program_id=output_msg.get('program_id'))