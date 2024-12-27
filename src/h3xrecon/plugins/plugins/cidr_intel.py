from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_domain_data, send_ip_data
from loguru import logger
import asyncio
import json
import os

class CIDRIntel(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    @property
    def sample_output(self) -> Dict[str, Any]:
        output_data = {
            "program_id": 1,
            "execution_id": "123",
            "source": {
                "function": "cidr_intel",
                "target": "1.1.0.0/16",
                "force": False
            },
            "output": {
                "domain": "example.com",
                "ip": "1.1.1.1"
            },
            "timestamp": "2024-01-01T00:00:00Z"
        }
        return output_data

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        command = f"amass intel -active -cidr {params.get("target", {})} -ipv4"
        logger.debug(f"Running command: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            try:
                json_data = {
                    "domain": output.split(" ")[0],
                    "ip": output.split(" ")[1]
                }
                logger.debug(f"Output: {json_data}")
                yield json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        try:
            domain = output_msg.get('output').get('domain')
            ip = output_msg.get('output').get('ip')
            if isinstance(ip, str):
                try:
                    await send_ip_data(qm=qm, data=ip, program_id=output_msg.get('program_id'))
                    logger.debug(f"Sent IP {ip} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
                except Exception as e:
                    logger.error(f"Error processing IP {ip}: {str(e)}")
            else:
                logger.warning(f"Unexpected IP format: {ip}")
            await send_domain_data(qm=qm, data=domain, program_id=output_msg.get('program_id'))
            logger.debug(f"Sent domain {domain} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
        except Exception as e:
            logger.error(f"Error in process_resolved_domain: {str(e)}")
            logger.exception(e)