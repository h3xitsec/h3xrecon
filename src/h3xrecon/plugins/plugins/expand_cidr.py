from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import batch_dispatch_jobs
from loguru import logger
import os

class ExpandCIDR(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 9999

    @property
    def target_types(self) -> List[str]:
        return ["cidr"]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, trigger_new_jobs: bool = True, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Expands the CIDR to individual IP addresses using prips and dispatches reverse_resolve_ip tasks.
        
        :param target: The CIDR range (e.g., "192.168.1.0/24")
        """
        logger.debug(f"Running {self.name} on CIDR: {params.get('target', {})}")
        logger.debug("Dispatching amass task for the CIDR")
        # Dispatch amass task for the CIDR
        await qm.publish_message(
            subject="recon.input.amass",
            stream="RECON_INPUT",
            message={
                "function_name": "amass",
                "program_id": program_id,
                "params": {"target": params.get("target", {})},
                "force": False,
                "trigger_new_jobs": False,
                "execution_id": execution_id
            }
        )
        command = f"prips {params.get('target', {})} && cat /tmp/prips.log"
        logger.debug(f"Running command: {command}")
        stdout, stderr = self._create_subprocess_shell_sync(command)
        if stderr:
            logger.warning(f"prips stderr output: {stderr}")
        ips = stdout.split()
        
        # Process IPs in chunks using the batch_dispatch_jobs helper
        logger.debug(f"Dispatching reverse_resolve_ip tasks for {len(ips)} IPs")
        await batch_dispatch_jobs(
            qm=qm,
            items=ips,
            function_name="reverse_resolve_ip",
            program_id=program_id,
            execution_id=execution_id,
            chunk_size=100,
            delay=0.1
        )
        
        yield {}
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        return {}