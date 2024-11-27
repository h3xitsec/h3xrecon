from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from loguru import logger
from dataclasses import dataclass, asdict
import asyncio
import json
import os

# TODO: remove the default template_id
@dataclass
class FunctionParams():
    target: str
    template_id: str = "insecure-cipher-suite-detect"

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
            "program_id": 1,
            "execution_id": "sample-execution-id",
            "source": {
                "function": "nuclei",
                "target": "example.com",
                "force": False
            },
            "output": {
                "url": "https://example.com",
                "matched_at": "https://example.com",
                "type": "http",
                "ip": "1.1.1.1",
                "port": 443,
                "template_path": "http/technologies/sample-detect.yaml",
                "template_id": "sample-detect",
                "template_name": "sample cdn detection",
                "severity": "info"
            },
            "timestamp": "2024-01-01T00:00:00+00:00"
        }

        return output_data

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        function_params = FunctionParams(**params)
        logger.info(f"Running {self.name} on {function_params.target}")
        # TODO: add more scan options to be sent from the client
        # FIXME: remove the full path to the nuclei binary
        command = f"""
            /home/h3x/.pdtm/go/bin/nuclei -u {function_params.target} -j -as
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
        from h3xrecon.core import Config
        from h3xrecon.core import QueueManager
        
        self.config = Config()
        self.qm = QueueManager(self.config.nats)
        logger.debug(f"Incoming message:\nObject Type: {type(output_msg)}\nObject:\n{json.dumps(output_msg, indent=4)}")
        
        nuclei_msg = {
            "program_id": output_msg.get('program_id'),
            "data_type": "nuclei",
            "data": [output_msg.get('output')]
        }
        # TODO: add more data to send to the dataprocessor (url, domain, ip, service, etc.)
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=nuclei_msg)
