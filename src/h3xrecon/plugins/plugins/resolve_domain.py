from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import *
from h3xrecon.plugins.helper import send_ip_data, send_domain_data
from loguru import logger
import asyncio
import json
import os

class ResolveDomain(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, ) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {params.get("target", {})}")
        command = f"echo {params.get("target", {})} | dnsx -nc -resp -a -cname -silent -j | jq -Mc '{{host: .host,a_records: (.a // []),cnames: (.cname // [])}}'"
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
                logger.debug(f"Parsed output: {json_data}")
                yield json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        self.config = Config()
        self.db = db #DatabaseManager(self.config.database.to_dict())
        self.qm = QueueManager(self.config.nats)
        try:
            #if await self.db.check_domain_regex_match(output_msg.get('output').get('host'), output_msg.get('program_id')):
            if isinstance(output_msg.get('output').get('a_records'), list):
                for ip in output_msg.get('output').get('a_records'):
                    if isinstance(ip, str):
                        try:
                            await send_ip_data(data=ip, program_id=output_msg.get('program_id'))
                            logger.debug(f"Sent IP {ip} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
                        except Exception as e:
                            logger.error(f"Error processing IP {ip}: {str(e)}")
                    else:
                        logger.warning(f"Unexpected IP format: {ip}")
            else:
                logger.warning(f"Unexpected IP format: {output_msg.get('output').get('a_records')}")
            #if output_msg.get('output', {}).get('cnames'):
            await send_domain_data(data=output_msg.get('source', {}).get('params', {}).get('target'), program_id=output_msg.get('program_id'), attributes={"cnames": output_msg.get('output', {}).get('cnames'), "ips": output_msg.get('output', {}).get('a_records')})
            logger.debug(f"Sent domain {output_msg.get('source', {}).get('params', {}).get('target')} to data processor queue for domain {output_msg.get('source', {}).get('params',{}).get('target')}")
            #else:
            #    logger.info(f"Domain {output_msg.get('output').get('host')} is not part of program {output_msg.get('program_id')}. Skipping processing.")
        except Exception as e:
            logger.error(f"Error in process_resolved_domain: {str(e)}")
            logger.exception(e)