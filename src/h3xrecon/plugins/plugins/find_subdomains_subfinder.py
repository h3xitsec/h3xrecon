from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import *
from loguru import logger
import asyncio
import os

class FindSubdomainsSubfinder(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str, program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {target}")
        command = f"subfinder -d {target}"
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
        logger.info(f"Finished {self.name} on {target}")
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        self.config = Config()
        self.qm = QueueManager(self.config.nats)
        domain_msg = {
            "program_id": output_msg.get('program_id'),
            "data_type": "domain",
            "in_scope": output_msg.get('in_scope'),
            "data": output_msg.get('output', {}).get('subdomain')
        }
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=domain_msg)