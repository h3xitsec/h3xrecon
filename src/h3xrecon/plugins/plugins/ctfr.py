from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from loguru import logger
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url
from h3xrecon.plugins.helper import send_domain_data
import os
class CTFRPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 120
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
    
    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get('target', {})}")
        command = f"python /opt/ctfr/ctfr.py -d {params.get('target', {})} -o /tmp/ctfr.log > /dev/null 2>&1 && cat /tmp/ctfr.log | grep -Ev '.*\\*.*' | sort -u && rm /tmp/ctfr.log"
        
        process = None
        try:
            stdout, stderr = self._create_subprocess_shell_sync(command)
            valid_subdomains = []
            for i in stdout.split("\n"):
                if is_valid_hostname(i):
                    logger.debug(f"Output: {i}")
                    valid_subdomains.append(i)
            yield {"subdomain": valid_subdomains}
                
        except Exception as e:
            logger.error(f"Error during {self.name} execution: {str(e)}")
            if process:
                process.kill()
            raise
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        for subdomain in output_msg.get("data", {}).get('subdomain', []):
            await send_domain_data(qm=qm, 
                                   data=subdomain, 
                                   program_id=output_msg.get('program_id'), 
                                   execution_id=output_msg.get('execution_id'), 
                                   trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
        return {}