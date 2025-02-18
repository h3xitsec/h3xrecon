from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import unclutter_url_list
from h3xrecon.core.utils import is_valid_hostname
from loguru import logger
import os
from time import sleep

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
        tmp_file = f"/tmp/{execution_id}_{self.name}.txt"
        # Get URLs
        command = f"echo {params.get('target', {})} | gau --blacklist png,jpg,gif,jpeg,swf,woff,woff2,eot,ttf,svg,css,ico,tif,tiff --subs --o {tmp_file}"
        logger.debug(f"Running command: {command}")
        stdout, stderr = self._create_subprocess_shell_sync(command)
        if stderr:
            logger.warning(f"gau stderr output: {stderr}")
        with open(tmp_file, "r") as f:
            urls = [url.strip() for url in f.readlines()]
        logger.debug(f"Gau found {len(urls)} urls")
        urls = unclutter_url_list(urls)
        logger.debug(f"Uncluttered urls: {len(urls)}")
        # Extract domains from URLs
        command = f"echo '{"\n".join(urls)}' | unfurl -u domains | sort -u"
        logger.debug(f"Running command: {command}")
        stdout, stderr = self._create_subprocess_shell_sync(command)
        if stderr:
            logger.warning(f"unfurl stderr output: {stderr}")
        domains = stdout.splitlines()
        logger.debug(f"Domains: {domains}")
        logger.info(f"DISPATCHING JOBS: httpx for {len(urls)} urls")
        for url in urls:
        # Dispatch httpx jobs for each url
            await qm.publish_message(
                subject="recon.input.httpx",
                stream="RECON_INPUT",
                message={
                    "function_name": "httpx",
                    "program_id": program_id,
                    "params": {"target": url},
                    "force": False,
                    "execution_id": execution_id,
                    "trigger_new_jobs": False
                }
            )
            sleep(0.5)
        # Dispatch puredns and dnsx jobs for each domain
        for domain in domains:
            logger.info(f"DISPATCHING JOB: puredns for {domain}")
            await qm.publish_message(
                subject="recon.input.puredns",
                stream="RECON_INPUT",
                message={
                    "function_name": "puredns",
                    "program_id": program_id,
                    "params": {"target": domain, "mode": "resolve"},
                    "force": False,
                    "execution_id": execution_id,
                    "trigger_new_jobs": False
                }
            )
            sleep(0.5)
        for domain in domains:
            logger.info(f"DISPATCHING JOB: dnsx for {domain}")
            await qm.publish_message(
                subject="recon.input.dnsx",
                stream="RECON_INPUT",
                message={
                    "function_name": "dnsx",
                    "program_id": program_id,
                    "params": {"target": domain},
                    "force": False,
                    "execution_id": execution_id,
                    "trigger_new_jobs": False
                }
            )
            sleep(0.5)
        yield {}
        
        

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        return {}
