from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from loguru import logger
from dataclasses import dataclass, asdict, field
from h3xrecon.plugins.helper import send_nuclei_data, send_ip_data, send_domain_data, send_service_data
from urllib.parse import urlparse
import asyncio
import json
import os
from pydantic import BaseModel, Field, IPvAnyAddress, AnyHttpUrl, constr
from typing import Union, Optional

@dataclass
class FunctionParams():
    target: str
    extra_params: list = field(default_factory=list)

class FunctionOutput(BaseModel):
    url: Union[AnyHttpUrl, str] = Field(pattern=r'^(https?://[^\s]+|\d+\.\d+\.\d+\.\d+:\d+)$')
    matched_at: Union[AnyHttpUrl, str] = Field(pattern=r'^(https?://[^\s]+|\d+\.\d+\.\d+\.\d+:\d+)$')
    type: str = Field(pattern='^(http|tcp|udp)$')
    ip: str = Field(pattern=r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$|^[0-9a-fA-F:]+$')
    port: int = Field(ge=1, le=65535)
    scheme: Optional[str] = Field(default=None, pattern='^(http|https|ftp|ssh|tcp|udp)?$')
    template_path: str
    template_id: str
    template_name: str
    severity: str = Field(pattern='^(info|low|medium|high|critical)$')

    class Config:
        json_encoders = {
            IPvAnyAddress: str
        }

class Nuclei(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        function_params = asdict(FunctionParams(**params))
        logger.info(f"Running {self.name} on {function_params.get('target', {})}")
        command = f"""
            nuclei -or -u {function_params.get('target', {})} -j {" ".join(function_params.get('extra_params', []))}
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
                ip_str = str(json_data.get('ip', ''))
                nuclei_output = FunctionOutput(
                    url=json_data.get('url', ''),
                    matched_at=json_data.get('matched-at', ''),
                    type=json_data.get('type', ''),
                    ip=ip_str,
                    port=json_data.get('port', 0),
                    scheme=json_data.get('scheme', ''),
                    template_path=json_data.get('template', ''),
                    template_id=json_data.get('template-id', ''),
                    template_name=json_data.get('info', {}).get('name', ''),
                    severity=json_data.get('info', {}).get('severity', 'info')
                )
                yield nuclei_output.model_dump()
            except Exception as e:
                logger.error(f"Error processing Nuclei output: {e}")
                yield {}

        await process.wait()
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        #if output_msg.get('in_scope', False):
        if output_msg.get('output', {}).get('type', "") == "http":
            hostname = urlparse(output_msg.get('output', {}).get('url', "")).hostname            
        else:
            hostname = output_msg.get('output', {}).get('url', "").split(":")[0]
        await send_domain_data(data=hostname, program_id=output_msg.get('program_id'))
        await send_ip_data(data=output_msg.get('output', {}).get('ip', ""), program_id=output_msg.get('program_id'))
        await send_nuclei_data(data=output_msg.get('output', {}), program_id=output_msg.get('program_id'))
        # Find scheme and protocol

        if output_msg.get('output').get('type') == "http":
            protocol = "tcp"
            scheme = output_msg.get('output').get('scheme', "")
        else:
            protocol = output_msg.get('output').get('type', "")
            scheme = output_msg.get('output').get('scheme', "")
        service = {
            "ip": output_msg.get('output').get('ip'),
            "port": int(output_msg.get('output').get('port')),
            "protocol": protocol,
            "state": "open",
            "service": scheme,
        }
        await send_service_data(data=service, program_id=output_msg.get('program_id'))