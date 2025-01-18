from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_ip_data, send_domain_data, parse_dns_record, send_dns_data
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url
from loguru import logger
import asyncio
import json
import os

FILES_PATH = os.environ.get('H3XRECON_RECON_FILES_PATH')
RESOLVERS_FILE = f"{FILES_PATH}/resolvers.txt"
RESOLVERS_TRUSTED_FILE = f"{FILES_PATH}/resolvers-trusted.txt"
BRUTEFORCE_WORDLIST = f"{FILES_PATH}/subdomains.txt"

class PureDNSPlugin(ReconPlugin):
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

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        if not params.get("mode"):
            logger.error("Run mode not specified")
            return
        run_mode = params.get("mode")
        logger.debug(f"Running {self.name} ({run_mode} mode) on {params.get("target", {})}")
        puredns_command = None
        if run_mode == "resolve":
            puredns_command = f"puredns resolve /tmp/puredns_target.txt \
                --resolvers {RESOLVERS_FILE} \
                --resolvers-trusted {RESOLVERS_TRUSTED_FILE} \
                --write-massdns /tmp/puredns.txt > /dev/null 2>&1"
        
        elif run_mode == "bruteforce":
            puredns_command = f"puredns bruteforce {BRUTEFORCE_WORDLIST} \
                -d /tmp/puredns_target.txt \
                --resolvers {RESOLVERS_FILE} \
                --resolvers-trusted {RESOLVERS_TRUSTED_FILE} \
                --write-massdns /tmp/puredns.txt > /dev/null 2>&1"
        
        elif run_mode == "custom":
            puredns_command = f"puredns \
                {" ".join(params.get('extra_params', []))} \
                --write-massdns /tmp/puredns.txt > /dev/null 2>&1"
        else:
            raise ValueError(f"Invalid mode: {run_mode}")
        if not puredns_command:
            raise ValueError(f"Invalid puredns command")
        command = f"echo {params.get("target", {})} > /tmp/puredns_target.txt && {puredns_command} && cat /tmp/puredns.txt && rm -f /tmp/puredns_target.txt && rm -f /tmp/puredns.txt"
        logger.debug(f"Running command: {command}")
        process = await self._create_subprocess_shell(command)
        
        async for output in self._read_subprocess_output(process):
            try:
                logger.debug(f"Output: {output}")
                yield output
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        logger.debug(f"Processing output: {output_msg}")
        try:
            # Get the raw output string
            raw_output = output_msg.get('output', '')
            logger.debug(f"Raw output: {raw_output}")
            if not raw_output:
                return

            # Parse the DNS record directly
            # Format example: "promotion.portofantwerp.com. A 188.118.8.16"
            parts = raw_output.strip().split()
            if len(parts) < 3:
                return

            # Remove trailing dot from domain name
            name = parts[0].rstrip('.')
            record_type = parts[1]
            value = parts[2]

            parsed_record = {
                'hostname': name,
                'dns_type': record_type,
                'value': value,
                'ttl': 0,
                'dns_class': '?IN?',
                'target_domain': output_msg.get('source', {}).get('params', {}).get('target')
            }
            logger.debug(f"Parsed record: {parsed_record}")
            # Send DNS record data
            await send_dns_data(
                qm=qm,
                data=parsed_record,
                program_id=output_msg.get('program_id'),
                trigger_new_jobs=output_msg.get('trigger_new_jobs', False),
                execution_id=output_msg.get('execution_id')
            )
            logger.debug(f"Sent DNS record {parsed_record} to data processor queue")

            # If it's an A record, send IP data
            if record_type == 'A':
                await send_ip_data(
                    qm=qm,
                    data=value,
                    program_id=output_msg.get('program_id'),
                    trigger_new_jobs=output_msg.get('trigger_new_jobs', True),
                    execution_id=output_msg.get('execution_id')
                )
                logger.debug(f"Sent IP {value} to data processor queue")

            # Send domain data
            await send_domain_data(
                qm=qm,
                data=name,
                execution_id=output_msg.get('execution_id'),
                program_id=output_msg.get('program_id'),
                attributes={
                    "cnames": [value] if record_type == 'CNAME' else None,
                    "ips": [value] if record_type == 'A' else None
                },
                trigger_new_jobs=output_msg.get('trigger_new_jobs', True)
            )
            logger.debug(f"Sent domain {name} to data processor queue")

        except Exception as e:
            logger.error(f"Error in process_output: {str(e)}")
            logger.exception(e)