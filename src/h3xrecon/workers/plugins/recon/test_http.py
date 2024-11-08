from typing import AsyncGenerator, Dict, Any
from h3xrecon.workers.plugins.base import ReconPlugin
from loguru import logger
import asyncio
import json
import os

class TestHTTP(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {target}")
        command = f"""
            #!/bin/bash
            httpx -u {target} \
                -fr \
                -silent \
                -status-code \
                -content-length \
                -tech-detect \
                -threads 50 \
                -no-color \
                -json \
                -p 80 \
                #-p 80-99,443-449,11443,8443-8449,9000-9003,8080-8089,8801-8810,3000,5000 \
                -efqdn \
                -tls-grab \
                -pa \
                -tls-probe \
                -pipeline \
                -http2 \
                -vhost \
                -bp \
                -ip \
                -cname \
                -asn \
                -random-agent
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