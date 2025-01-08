from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_domain_data
from h3xrecon.core.utils import parse_url, is_valid_hostname, get_domain_from_url
from loguru import logger
import os
import dns.resolver
import random
import string

class TestDomainCatchall(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["domain"]

    
    def random_string(self, length=10):
        """Generate a random string of fixed length."""
        letters = string.ascii_lowercase
        return ''.join(random.choice(letters) for i in range(length))
    
    async def is_valid_input(self, params: Dict[str, Any]) -> bool:
        return is_valid_hostname(params.get("target", {}))
    
    def check_catchall(self, domain, resolver=None):
        """Check if a domain is a DNS catchall."""
        random_subdomain = f"{self.random_string()}.{domain}"
        try:
            resolver.resolve(random_subdomain, 'A')
            return True
        except dns.resolver.NXDOMAIN:
            return False
        except dns.resolver.NoAnswer:
            return False
        except dns.resolver.Timeout:
            return False
        except Exception:
            return False
    
    async def format_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not is_valid_hostname(params.get("target", {})):
            if params.get("target", {}).startswith("https://") or params.get("target", {}).startswith("http://"):
                params["target"] = get_domain_from_url(params.get("target", {}))
            else:
                params["target"] = params.get("target", {})
        return params
    
    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8']  # Using Google's DNS server, you can change this if needed
        
        is_catchall = self.check_catchall(params.get("target", {}), resolver)
        if params.get("target", {}).startswith("https://") or params.get("target", {}).startswith("http://"):
            domain = parse_url(params.get("target", {})).get("website", {}).get("host", None)
        else:
            domain = params.get("target", None)
        if domain is None:
            logger.error(f"Domain not found in {params.get('target', {})}")
            raise Exception(f"Domain not found in {params.get('target', {})}")
        result = {
            "domain": domain,
            "is_catchall": is_catchall
        }
        
        yield result
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        #if await self.db.check_domain_regex_match(output_msg.get('source', {}).get('params',{}).get('target'), output_msg.get('program_id')):
        #if await self.db.check_domain_regex_match(output_msg.get('source', {}).get('params',{}).get('target'), output_msg.get('program_id')):
        #logger.info(f"Domain {output_msg.get('source', {}).get('params',{}).get('target')} is part of program {output_msg.get('program_id')}. Sending to data processor.")
        await send_domain_data(qm=qm, data=output_msg.get('output', {}).get('domain'), program_id=output_msg.get('program_id'), attributes={"is_catchall": output_msg.get('output', {}).get('is_catchall')})
        # msg = {
        #     "program_id": output_msg.get('program_id'),
        #     "data_type": "domain",
        #     "data": output_msg.get('output', {}).get('domain'),
        #     "attributes": {
        #         "is_catchall": output_msg.get('output', {}).get('is_catchall')
        #     }
        # }
        # await self.qm.publish_message(subject="data.input", stream="DATA_INPUT", message=msg)

        # else:
        #     logger.info(f"Domain {output_msg.get('source', {}).get('params',{}).get('target')} is not part of program {output_msg.get('program_id')}. Skipping processing.")