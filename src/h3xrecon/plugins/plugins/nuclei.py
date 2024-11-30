from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from loguru import logger
from dataclasses import dataclass, asdict, field
import asyncio
import json
import os

@dataclass
class FunctionParams():
    target: str
    extra_params: list = field(default_factory=list)

@dataclass
class FunctionOutput():
    url: str
    matched_at: str
    type: str
    ip: str
    port: int
    template_path: str
    template_id: str
    template_name: str
    severity: str


class Nuclei(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    @property
    def sample_output(self) -> Dict[str, Any]:
        output_data = {
            "program_id": 245,
            "execution_id": "e3de832a-418a-458d-82d5-28c8def3229d",
            "source": {
                "function": "nuclei",
                "params": {
                    "target": "example.com",
                    "extra_params": ["-t", "http/technologies"]
                },
                "force": False
            },
            "output": {
                "url": "https://example.com",
                "matched_at": "https://example.com",
                "type": "http",
                "ip": "1.1.1.1",
                "port": 443,
                "scheme": "https",
                "template_path": "http/technologies/sample-detect.yaml",
                "template_id": "sample-detect",
                "template_name": "sample cdn detection",
                "severity": "info"
            },
            "timestamp": "2024-01-01T00:00:00+00:00"
        }

        return output_data

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        function_params = asdict(FunctionParams(**params))
        logger.info(f"Running {self.name} on {function_params.get("target", {})}")
        command = f"""
            nuclei -u {function_params.get("target", {})} -j {" ".join(function_params.get("extra_params", []))}
        """
        logger.debug(f"Running command: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            try:
                json_data = json.loads(output)
                logger.debug(f"Nuclei output: {json_data}")
                nuclei_output = FunctionOutput(
                    url=json_data.get('url', {}),
                    matched_at=json_data.get('matched-at', {}),
                    type=json_data.get('type', {}),
                    ip=json_data.get('ip', {}),
                    port=json_data.get('port', {}),
                    scheme=json_data.get('scheme', {}),
                    template_path=json_data.get('template', {}),
                    template_id=json_data.get('template-id', {}),
                    template_name=json_data.get('info', {}).get('name', {}),
                    severity=json_data.get('info', {}).get('severity', {})
                )
                yield asdict(nuclei_output)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        from h3xrecon.plugins.helper import send_nuclei_data, send_ip_data, send_domain_data, send_service_data
        from urllib.parse import urlparse
        if output_msg.get('in_scope', False):
            parsed_url = urlparse(output_msg.get('output').get('url'))
            await send_domain_data(data=parsed_url.netloc, program_id=output_msg.get('program_id'))
            await send_nuclei_data(data=output_msg.get('output'), program_id=output_msg.get('program_id'))
            await send_ip_data(data=output_msg.get('output').get('ip'), program_id=output_msg.get('program_id'))
            service = {
                "ip": output_msg.get('output').get('ip'),
                "port": output_msg.get('output').get('port'),
                "protocol": "tcp",
                "state": "open",
                "service": output_msg.get('output').get('scheme'),
            }
            await send_service_data(data=service, program_id=output_msg.get('program_id'))
        # nuclei_msg = {
        #     "program_id": output_msg.get('program_id'),
        #     "data_type": "nuclei",
        #     "data": [output_msg.get('output')]
        # }
        # TODO: add more data to send to the dataprocessor (url, domain, ip, service, etc.)
        #await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=nuclei_msg)
