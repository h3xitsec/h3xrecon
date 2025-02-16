from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import unclutter_url_list, batch_dispatch_jobs
from h3xrecon.core.utils import is_valid_hostname
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
        
        # Dispatch httpx jobs for URLs in batches
        logger.info(f"DISPATCHING JOBS: httpx for {len(urls)} urls")
        await batch_dispatch_jobs(qm, urls, "httpx", program_id, execution_id)
        
        # Dispatch puredns jobs for domains in batches
        logger.info(f"DISPATCHING JOBS: puredns for {len(domains)} domains")
        await batch_dispatch_jobs(qm, domains, "puredns", program_id, execution_id, chunk_size=50)
        
        # Dispatch dnsx jobs for domains in batches
        logger.info(f"DISPATCHING JOBS: dnsx for {len(domains)} domains")
        await batch_dispatch_jobs(qm, domains, "dnsx", program_id, execution_id, chunk_size=50)
        
        yield {}

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        return {}
