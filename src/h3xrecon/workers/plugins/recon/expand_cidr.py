from typing import AsyncGenerator, Dict, Any
from h3xrecon.workers.plugins.base import ReconPlugin
from loguru import logger
import asyncio
import os

class ExpandCIDR(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Expands the CIDR to individual IP addresses using prips and dispatches reverse_resolve_ip tasks.
        
        :param target: The CIDR range (e.g., "192.168.1.0/24")
        """
        logger.info(f"Running {self.name} on CIDR: {target}")
        command = f"""
            prips {target}
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        async for output in self._read_subprocess_output(process):
            # Prepare the message for reverse_resolve_ip
            message = {
                "function": "reverse_resolve_ip",
                "params": {
                    "target": output
                }
            }
            yield message

        await process.wait()