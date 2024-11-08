from typing import AsyncGenerator, Dict, Any
from h3xrecon.workers.plugins.base import ReconPlugin
from loguru import logger
import asyncio
import os

class SubdomainPermutation(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug("Checking if the target is a dns catchall domain")
        
        logger.info(f"Running {self.name} on {target}")
        command = f"""
            echo "{target}" > /tmp/gotator_input.txt
            gotator -sub /tmp/gotator_input.txt -perm /app/Worker/files/permutations.txt -depth 1 -numbers 10 -mindup -adv -md
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
                "function": "resolve_domain",
                "params": {
                    "target": output
                }
            }
            yield message

        await process.wait()