from typing import AsyncGenerator, Dict, Any
from plugins.base import ReconPlugin
from loguru import logger
import asyncio
import json
import os

class ResolveDomain(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {target}")
        command = f"""
            #!/bin/bash
            echo {target} | dnsx -nc -resp -a -cname -silent -j | jq -Mc '{{host: .host,a_records: (.a // []),cnames: (.cname // [])}}'
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            try:
                json_data = json.loads(output)
                yield json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()