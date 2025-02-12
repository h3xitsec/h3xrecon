from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from loguru import logger
import os

class ExpandCIDR(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["cidr"]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
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
        output = stdout.split()
        # Dispatch reverse_resolve_ip tasks for each IP of the CIDR
        for ip in output:
            await qm.publish_message(
                subject="recon.input.reverse_resolve_ip",
                stream="RECON_INPUT",
                message={
                    "function_name": "reverse_resolve_ip",
                    "program_id": program_id,
                    "params": {"target": ip},
                    "force": False,
                    "trigger_new_jobs": False,
                    "execution_id": execution_id
                }
            )
        # message = {
        #     "function_name": "reverse_resolve_ip",
        #     "target": output
        # }
        # logger.debug(f"Yielding message: {message}")
        # yield message
        # # Make the parsing worker dispatch "amass" job for the CIDR
        # message = {
        #     "function_name": "amass",
        #     "target": params.get("target", {})
        # }
        # logger.debug(f"Yielding message: {message}")
        yield {}
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        return {}