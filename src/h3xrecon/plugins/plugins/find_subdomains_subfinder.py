from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import *
from h3xrecon.plugins.helper import send_domain_data
from loguru import logger
import asyncio
import os

class FindSubdomainsSubfinder(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {params.get("target", {})}")
        command = f"subfinder -d {params.get("target", {})}"
        logger.debug(f"Running command: {command}")

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            logger.debug(f"Output: {output}")
            yield {"subdomain": [output]}

        await process.wait()
        logger.info(f"Finished {self.name} on {params.get("target", {})}")
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        for subdomain in output_msg.get('output', {}).get('subdomain', []):
            await send_domain_data(data=subdomain, program_id=output_msg.get('program_id'))
