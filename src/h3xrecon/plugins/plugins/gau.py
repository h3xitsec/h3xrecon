from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_domain_data, send_website_path_data
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url, is_valid_url
from loguru import logger
import os

class GauPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 30

    @property
    def target_types(self) -> List[str]:
        return ["domain"]
    
    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_hostname(params.get("target", {}))

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        command = f"echo {params.get("target", {})} | gau --subs"
        logger.debug(f"Running command: {command}")
        process = await self._create_subprocess_shell(command)
        async for output in self._read_subprocess_output(process):
            if output:
                yield {"url": output}

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        logger.debug(f"Processing output: {output_msg}")
        if not is_valid_url(output_msg.get('data', {}).get('url', "")):
            logger.warning(f"Invalid URL: {output_msg.get('data', {}).get('url', '')}")
        else:
            # Send website_path and domain data
            website_path_msg = {
                "url": output_msg.get('data', {}).get('url', ""),
                'host': output_msg.get('data', {}).get('host', ""),
                'port': output_msg.get('data', {}).get('port', ""),
                'scheme': output_msg.get('data', {}).get('scheme', ""),
                'techs': output_msg.get('data', {}).get('techs', []),
                'favicon_hash': output_msg.get('data', {}).get('favicon_hash', ""),
                'favicon_url': output_msg.get('data', {}).get('favicon_url', ""),
            }
            await send_website_path_data(qm=qm, data=website_path_msg, program_id=output_msg.get('program_id'), execution_id=output_msg.get('execution_id'))
            domain = get_domain_from_url(output_msg.get('data', {}).get('url', ""))
            if domain:
                await send_domain_data(qm=qm, data=domain, program_id=output_msg.get('program_id'), execution_id=output_msg.get('execution_id'))
                # Trigger puredns and dnsx jobs
                logger.info(f"RECON JOB REQUESTED: puredns for {domain}")
                await qm.publish_message(
                    subject="recon.input.puredns",
                    stream="RECON_INPUT",
                    message={
                        "function_name": "puredns",
                        "program_id": output_msg.get("program_id"),
                        "params": {"target": domain, "mode": "resolve"},
                        "force": False,
                        "execution_id": output_msg.get('execution_id', None),
                        "trigger_new_jobs": False
                    }
                )
            # Trigger httpx job
            logger.info(f"RECON JOB REQUESTED: httpx for {output_msg.get('data', {}).get('url', '')}")
            await qm.publish_message(
                subject="recon.input.httpx",
                stream="RECON_INPUT",
                message={
                    "function_name": "httpx",
                    "program_id": output_msg.get("program_id"),
                    "params": {"target": output_msg.get("data").get("url")},
                    "force": False,
                    "execution_id": output_msg.get('execution_id', None),
                    "trigger_new_jobs": False
                }
            )

        
