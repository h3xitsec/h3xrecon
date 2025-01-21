import os
from typing import Dict, Any, AsyncGenerator, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import Config, QueueManager
from loguru import logger
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url

__input_type__ = "domain"

class FindSubdomainsPlugin(ReconPlugin):
    """
    Meta plugin that triggers multiple subdomain discovery tools
    """
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["domain"]


    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_hostname(params.get("target", {}))
    
    async def format_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not is_valid_hostname(params.get("target", {})):
            if params.get("target", {}).startswith("https://") or params.get("target", {}).startswith("http://"):
                params["target"] = get_domain_from_url(params.get("target", {}))
            else:
                params["target"] = params.get("target", {})
        return params

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
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        await qm.publish_message(
            subject="recon.input",
            stream="RECON_INPUT",
            message={
                "function_name": output_msg.get("data").get("function_name"),
                "program_id": output_msg.get("program_id"),
                "params": {"target": output_msg.get("data").get("target")},
                "force": output_msg.get("source", {}).get("force", False),
                "trigger_new_jobs": output_msg.get("trigger_new_jobs"),
                "execution_id": output_msg.get("execution_id")
            }
        )