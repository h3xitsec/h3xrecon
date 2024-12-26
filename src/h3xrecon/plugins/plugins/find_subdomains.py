import os
from typing import Dict, Any, AsyncGenerator
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import Config, QueueManager
from loguru import logger


class FindSubdomainsPlugin(ReconPlugin):
    """
    Meta plugin that triggers multiple subdomain discovery tools
    """
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int, execution_id: str, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute the meta plugin by dispatching multiple subdomain discovery jobs
        """
        self.program_id = program_id
        self.execution_id = execution_id
        self.config = Config()
        self.qm = QueueManager(self.config.nats)
        # List of subdomain discovery tools to trigger
        subdomain_tools = [
            "find_subdomains_subfinder",
            "find_subdomains_ctfr"
        ]
        # Send jobs for each tool and yield dispatched job information
        for tool in subdomain_tools:
            job = {
                "function_name": tool,
                "target": params.get("target", {}),
            }
            logger.info(f"Dispatching job: {job}")
            logger.debug(f"Dispatching job: {job}")
            
            yield job
    
    async def send_job(self, function_name: str, program_id: int, target: str, force: bool):
        """Send a job to the worker using QueueManager"""

        message = {
            "force": force,
            "function": function_name,
            "program_id": program_id,
            "params": {"target": target}
        }
        logger.info(self.config.nats)
        await self.qm.publish_message(
            subject="function.execute",
            stream="FUNCTION_EXECUTE",
            message=message
        )
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        await qm.publish_message(
            subject="function.execute",
            stream="FUNCTION_EXECUTE",
            message={
                "function": output_msg.get("output").get("function_name"),
                "program_id": output_msg.get("program_id"),
                "params": {"target": output_msg.get("output").get("target")},
                "force": False
            }
        )