import os
from typing import Dict, Any, AsyncGenerator, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import Config, QueueManager
from loguru import logger
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url
from h3xrecon.plugins.helper import send_domain_data
from h3xrecon.plugins.plugins.subfinder import SubfinderPlugin
from h3xrecon.plugins.plugins.ctfr import CTFRPlugin
from h3xrecon.plugins.plugins.assetfinder import AssetfinderPlugin

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
        Execute the meta plugin by directly running multiple subdomain discovery plugins
        """
        self.program_id = program_id
        self.execution_id = execution_id
        self.config = Config()
        self.qm = QueueManager(self.config.nats)

        # Initialize plugins
        plugins = [
            SubfinderPlugin(),
            CTFRPlugin(),
            AssetfinderPlugin()
        ]

        # Set to store unique subdomains
        subdomains = set()

        # Execute each plugin and collect results
        for plugin in plugins:
            try:
                logger.info(f"Running {plugin.name} for {params.get('target', {})}")
                async for result in plugin.execute(params, program_id, execution_id, db, qm):
                    if result and "subdomain" in result:
                        # Add subdomains to the set
                        subdomains.update(result["subdomain"])
                        logger.debug(f"Subdomains: {subdomains}")
            except Exception as e:
                logger.error(f"Error running {plugin.name}: {str(e)}")
                continue

        # Yield the accumulated unique subdomains
        if subdomains:
            yield {"subdomain": list(subdomains)}
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        for subdomain in output_msg.get("data", {}).get("subdomain", []):
            logger.debug(f"Sending subdomain {subdomain} to data processor queue")
            await send_domain_data(qm=qm, 
                                data=subdomain, 
                                program_id=output_msg.get('program_id'), 
                                execution_id=output_msg.get('execution_id'), 
                                trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
        return {}