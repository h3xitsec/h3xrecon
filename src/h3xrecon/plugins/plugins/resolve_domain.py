import os
from typing import Dict, Any, AsyncGenerator, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import Config, QueueManager
from loguru import logger
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url

__input_type__ = "domain"

class ResolveDomainMetaPlugin(ReconPlugin):
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
        dns_tools = [
            "dnsx",
            "puredns"
        ]
        jobs = [
            {
                "function_name": "puredns",
                "params": {
                    "mode": "resolve",
                    "target": params.get("target", {})
                }
            },
            {
                "function_name": "dnsx",
                "params": {
                    "target": params.get("target", {})
                }
            },
            {
                "function_name": "test_domain_catchall",
                "params": {
                    "target": params.get("target", {})
                }
            }
        ]
        # Send jobs for each tool and yield dispatched job information
        for job in jobs:
            job["params"] = job.get("params", {})
            job['params']['target'] = params.get("target", {})
            job['program_name'] = self.program_id
            job['params']['extra_params'] = job.get("params", {}).get("extra_params", [])
            yield job
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        await qm.publish_message(
            subject="recon.input",
            stream="RECON_INPUT",
            message={
                "function_name": output_msg.get("output").get("function_name"),
                "program_id": output_msg.get("program_id"),
                "params": output_msg.get("output").get("params"),
                "force": output_msg.get("source", {}).get("force", False),
                "trigger_new_jobs": output_msg.get("trigger_new_jobs"),
                "execution_id": output_msg.get("execution_id")
            }
        )