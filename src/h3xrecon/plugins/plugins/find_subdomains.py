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

    async def execute(self, params: Dict[str, Any], program_id: int, execution_id: str, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute the meta plugin by dispatching multiple subdomain discovery jobs
        """
        self.program_id = program_id
        self.execution_id = execution_id
        self.config = Config()
        self.qm = QueueManager(self.config.nats)
        # List of subdomain discovery tools to trigger
        subdomain_tools = [
            "subfinder",
            "ctfr"
        ]
        # Send jobs for each tool and yield dispatched job information
        for tool in subdomain_tools:
            logger.info(f"Dispatching job: {tool}")
            await qm.publish_message(
                subject=f"recon.input.{tool}",
                stream="RECON_INPUT",
                message={
                    "function_name": tool,
                    "program_id": program_id,
                    "params": {"target": params.get("target", {})},
                    "force": False,
                    "trigger_new_jobs": False,
                    "execution_id": execution_id
                }
            )
        yield {}
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        return {}