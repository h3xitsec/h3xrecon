from typing import AsyncGenerator, Dict, Any
from h3xrecon.workers.plugins.base import ReconPlugin
from loguru import logger
import asyncio
import json
import os

class FindSubdomainsSubfinder(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
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