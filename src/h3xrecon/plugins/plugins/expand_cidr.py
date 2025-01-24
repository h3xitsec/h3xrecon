from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from loguru import logger
import asyncio
import os

class ExpandCIDR(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["cidr"]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Expands the CIDR to individual IP addresses using prips and dispatches reverse_resolve_ip tasks.
        
        :param target: The CIDR range (e.g., "192.168.1.0/24")
        """
        logger.debug(f"Running {self.name} on CIDR: {params.get('target', {})}")
        command = f"prips {params.get('target', {})} && cat /tmp/prips.log"
        output = self._create_subprocess_shell_sync(
            command
        ).split()
        message = {
            "function_name": "reverse_resolve_ip",
            "target": output
        }
        logger.debug(f"Yielding message: {message}")
        yield message
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        logger.debug(f"Processing output: {output_msg}")
        for ip in output_msg.get("data").get("target"):
            await qm.publish_message(
                subject=f"recon.input.{output_msg.get("data").get("function_name")}",
                stream="RECON_INPUT",
                message={
                    "function_name": output_msg.get("data").get("function_name"),
                    "program_id": output_msg.get("program_id"),
                    "params": {"target": ip},
                    "force": False
                }
            )
        return {}