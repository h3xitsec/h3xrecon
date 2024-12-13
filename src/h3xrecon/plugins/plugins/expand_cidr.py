from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import *
from loguru import logger
import asyncio
import os

class ExpandCIDR(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Expands the CIDR to individual IP addresses using prips and dispatches reverse_resolve_ip tasks.
        
        :param target: The CIDR range (e.g., "192.168.1.0/24")
        """
        logger.info(f"Running {self.name} on CIDR: {params.get('target', {})}")
        command = f"prips {params.get('target', {})} && cat /tmp/prips.log"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        async for output in self._read_subprocess_output(process):
            # Prepare the message for reverse_resolve_ip
            message = {
                "function_name": "reverse_resolve_ip",
                "target": output
            }
            yield message

        await process.wait()
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        await qm.publish_message(
            subject="function.execute",
            stream="FUNCTION_EXECUTE",
            message={
                "function": output_msg.get("output").get("function_name"),
                "program_id": output_msg.get("program_id"),
                "params": {"target": output_msg.get("output").get("target")},
                "force": False
            }
        )