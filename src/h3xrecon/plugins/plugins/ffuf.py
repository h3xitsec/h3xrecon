from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_website_path_data, send_website_data
from h3xrecon.core.utils import parse_url, is_valid_url
from loguru import logger
import asyncio
import json
import os
import requests
import uuid

class FfufPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["url"]
    
    @property
    def timeout(self) -> int:
        return 300  # 5 minutes timeout
    
    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_url(params.get("target", {}))
    
    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, trigger_new_jobs: bool = True, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        parsed_url = parse_url(params.get('target', {}))
        target_url = parsed_url.get('website_path', {}).get('url')
        wordlist = params.get('wordlist', "/app/Worker/files/webcontent_test.txt")
        tmp_list = False
        if wordlist.startswith("http"):
            wl_content = requests.get(wordlist).text
            tmp_list = True
            wordlist = f"/tmp/{uuid.uuid4()}.txt"
            with open(wordlist, "w") as f:
                f.write(wl_content)
        if not os.path.exists(wordlist):
            logger.error(f"Wordlist {wordlist} does not exist")
            raise FileNotFoundError(f"Wordlist {wordlist} does not exist")
        logger.debug(f"Using wordlist {wordlist}")
        if target_url.endswith('/'):
            target_url = target_url[:-1]
        logger.debug(f"Running {self.name} on {target_url}")
        command = (
            f"ffuf -u {target_url}/FUZZ -w {wordlist} -s -json"
        )
        logger.debug(f"Command: {command}")
        process = None
        try:
            process = await self._create_subprocess_shell(command)
            
            try:
                while True:
                    try:
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.1)
                        if not line:
                            break
                            
                        try:
                            logger.debug(f"Line: {line.decode()}")
                            json_data = json.loads(line.decode())
                            yield json_data
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse JSON output: {e}")
                            
                    except asyncio.TimeoutError:
                        # Just continue the loop on timeout
                        continue
                        
            except Exception as e:
                raise
                
            await process.wait()
            if tmp_list:
                os.remove(wordlist)
        except Exception as e:
            logger.error(f"Error during HTTP test: {str(e)}")
            if process:
                process.kill()
            raise
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        logger.debug(f"Incoming message:\nObject Type: {type(output_msg)} : {json.dumps(output_msg)}")
        data = output_msg.get("data", {})
        parsed_website_and_path = parse_url(data.get('url', {}))
        website_msg = parsed_website_and_path.get('website', {})
        await send_website_data(qm=qm, 
                               data=website_msg, 
                               program_id=output_msg.get('program_id', None), 
                               execution_id=output_msg.get('execution_id', ""),
                               trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
        website_path_msg = parsed_website_and_path.get('website_path', {})
        website_path_msg['content_type'] = data.get('content-type', "")
        website_path_msg['status_code'] = data.get('status', None)
        website_path_msg['content_length'] = data.get('length', None)
        website_path_msg['final_path'] = data.get('redirectlocation', None)
        await send_website_path_data(qm=qm, 
                                     data=website_path_msg, 
                                     program_id=output_msg.get('program_id', None), 
                                     execution_id=output_msg.get('execution_id', ""),
                                     trigger_new_jobs=output_msg.get('trigger_new_jobs', True))