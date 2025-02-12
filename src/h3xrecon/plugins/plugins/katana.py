from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core.utils import is_valid_url, parse_url
from h3xrecon.plugins.helper import send_website_path_data
from loguru import logger
import os
import json
import asyncio
import hashlib
from bs4 import BeautifulSoup
import re

class KatanaPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 30

    @property
    def target_types(self) -> List[str]:
        return ["url"]
    
    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_url(params.get("target", {}))

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        command = f"katana -u {params.get("target", {})} -d 5 -jc -jsl -j -ct {self.timeout}"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        async for output in self._read_subprocess_output(process):
            logger.debug(output)
            try:
                json_data = json.loads(output)
                yield json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON output: {e}")
        
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        logger.debug(output_msg)
        msg_data = output_msg.get("data", {})
        if not msg_data or not msg_data.get("request") or not msg_data.get("response"):
            return {}

        # Parse URLs
        endpoint_url = msg_data["request"]["endpoint"]
        
        # Parse the endpoint URL to get website and path information
        parsed_data = parse_url(endpoint_url)
        if not parsed_data:
            logger.error(f"Error parsing URL: {endpoint_url}")
            return {}
        # Get response data
        
        response = msg_data["response"]
        if not response.get("status_code", None):
            return {}
        headers = response.get("headers", {})
        body = response.get("body", "")
        # Extract scheme from the URL
        scheme = endpoint_url.split("://")[0] if "://" in endpoint_url else None
        
        # Calculate response time from headers if available
        # response_time = None
        # if "x-timer" in headers:
        #     try:
        #         # Extract timing information from x-timer header
        #         timer_parts = headers["x-timer"].split(",")
        #         if len(timer_parts) >= 2:
        #             response_time = timer_parts[1].strip()
        #     except:
        #         pass
        # Parse HTML content if it's HTML
        title = None
        techs = []
        if body and "text/html" in headers.get("content-type", "").lower():
            try:
                soup = BeautifulSoup(body, 'html.parser')
                # Extract title
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.string.strip()
                
                # Extract potential technologies from meta tags
                meta_generator = soup.find('meta', attrs={'name': 'generator'})
                if meta_generator and meta_generator.get('content'):
                    techs.append(meta_generator['content'])
            except Exception as e:
                logger.error(f"Error parsing HTML: {e}")
        
        # Calculate hashes
        resp_header_hash = hashlib.sha256(json.dumps(headers, sort_keys=True).encode()).hexdigest() if headers else None

        # Change the body string so the hash matches httpx's
        body = body.replace("\\'", "'")
        body = body.replace("\\n", "")
        resp_body_hash = hashlib.sha256(body.encode()).hexdigest() if body else None

        website_path_data = {
            "url": endpoint_url,
            "path": parsed_data.get("website_path", {}).get('path', {}),
            "method": msg_data.get("request", {}).get("method", None),
            "status_code": response.get("status_code", None),
            "content_type": headers.get("content-type", None),
            "content_length": response.get("content_length", None),
            "scheme": scheme,
            "response_time": None,
            "techs": techs,
            "page_type": None,
            "resp_header_hash": resp_header_hash,
            "resp_body_hash": resp_body_hash,
            "chain_status_codes": [response.get("status_code", None)],
            "body_preview": None,
            "title": title,
            "lines": None,
            "words": None,
        }
        
        # Send the data through the helper function
        await send_website_path_data(qm=qm, 
                                    data=website_path_data, 
                                    program_id=output_msg.get('program_id', ""),
                                    trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
        #return website_path_data
