from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_screenshot_data, send_website_data, send_domain_data, send_website_path_data
from h3xrecon.core.utils import parse_url, is_valid_url
from loguru import logger
import os
import base64
import tarfile
import tempfile
import re
import shutil

class Screenshot(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 60
    @property
    def target_types(self) -> List[str]:
        return ["url"]

    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_url(params.get("target", {}))
    
    
    @property
    def timeout(self) -> int:
        return 300  # 5 minutes timeout

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get('target', {})}")
        command = f"""
            tmp=$(mktemp -d)
            gowitness scan single -u "{params.get('target', {})}" -s $tmp --quiet --screenshot-format png
            (
                cd $tmp
                if [ "$(ls -l *.png 2>/dev/null | wc -l)" -gt 0 ]
                then
                    tar czf $tmp/output.tar.gz ./*.png
                    base64 $tmp/output.tar.gz | tr -d '\n'
                fi
            )
            rm -rf $tmp
        """
        process = None
        try:
            process = await self._create_subprocess_shell(command)
            
            # Read the entire output at once instead of line by line
            stdout, stderr = await process.communicate()
            
            if stdout:
                # Calculate size of base64 data in KB
                data_size_kb = len(stdout) / 1024
                logger.debug(f"Screenshot data size: {data_size_kb:.2f} KB")
                # Yield the entire base64 encoded data
                yield {"data": stdout.decode().strip(), "size": float(f"{data_size_kb:.2f}")}
            
            if stderr:
                logger.error(f"Screenshot stderr: {stderr.decode()}")
                
            if process.returncode != 0:
                raise Exception(f"Screenshot process failed with return code {process.returncode}")
                
        except Exception as e:
            logger.error(f"Error during screenshot: {str(e)}")
            if process and process.returncode is None:
                process.kill()
            raise
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        SCREENSHOT_STORAGE_PATH = os.path.join(os.getenv('H3XRECON_SCREENSHOT_PATH', '/app/screenshots'), str(output_msg.get('program_id', {})))
        if not os.path.exists(SCREENSHOT_STORAGE_PATH):
            os.makedirs(SCREENSHOT_STORAGE_PATH)
        base64_archive = output_msg.get("data", {}).get('data')
        if base64_archive:
            archive_data = base64.b64decode(base64_archive)
            with tempfile.TemporaryDirectory() as temp_dir:
                logger.debug(f"Extracting screenshots to {temp_dir}")
                os.makedirs(temp_dir, exist_ok=True)
                try:
                    logger.debug(f"Writing archive data to {os.path.join(temp_dir, 'output_parser.tar.gz')}")
                    with open(os.path.join(temp_dir, 'output_parser.tar.gz'), 'wb') as f:
                        f.write(archive_data)
                    with tarfile.open(os.path.join(temp_dir, 'output_parser.tar.gz'), 'r:gz') as tar:
                        tar.extractall(path=temp_dir)
                    os.remove(os.path.join(temp_dir, 'output_parser.tar.gz'))
                    screenshots = [file for file in os.listdir(temp_dir) if re.match(r'.*\.png', file)]
                    parsed_website_and_path = parse_url(output_msg.get('source', {}).get('params', {}).get('target'))
                    #logger.debug(f"PARSED WEBSITE AND PATH: {parsed_website_and_path}")
                    if not parsed_website_and_path:
                        logger.error(f"Error parsing URL: {output_msg.get('source', {}).get('params', {}).get('target')}")
                        return
                    if parsed_website_and_path.get('website'):
                        #logger.debug(f"Sending website data: {parsed_website_and_path.get('website')}")
                        await send_website_data(qm=qm, 
                                                data=parsed_website_and_path.get('website'), 
                                                program_id=output_msg.get('program_id', ""), 
                                                trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
                    if parsed_website_and_path.get('website_path'):
                        #logger.debug(f"Sending website path data: {parsed_website_and_path.get('website_path')}")
                        await send_website_path_data(qm=qm, 
                                                     data=parsed_website_and_path.get('website_path'), 
                                                     program_id=output_msg.get('program_id', ""), 
                                                     trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
                    # Send screenshots
                    #logger.debug(f"Found {len(screenshots)} screenshots")
                    for file in screenshots:
                        #logger.debug(f"Moving {file} to {SCREENSHOT_STORAGE_PATH}")
                        shutil.move(os.path.join(temp_dir, file), os.path.join(SCREENSHOT_STORAGE_PATH, file))
                        if file.endswith('.png'):
                            screenshot_msg = {
                                "url": output_msg.get('source', {}).get('params', {}).get('target'),
                                "path": os.path.join(SCREENSHOT_STORAGE_PATH, file),
                            }
                            #logger.debug(f"Sending screenshot data: {screenshot_msg}")
                            await send_screenshot_data(qm=qm, 
                                                       data=screenshot_msg, 
                                                       program_id=output_msg.get('program_id', ""), 
                                                       execution_id=output_msg.get('execution_id', ""), 
                                                       trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
                    
                    # Send domain data
                    try:
                        hostname = parsed_website_and_path.get('website').get('url')
                        domain_msg = hostname
                        await send_domain_data(qm=qm, 
                                               data=domain_msg, 
                                               program_id=output_msg.get('program_id', ""), 
                                               execution_id=output_msg.get('execution_id', ""), 
                                               trigger_new_jobs=output_msg.get('trigger_new_jobs', True))
                    except Exception as e:
                        logger.warning(f"Error extracting domain: {str(e)}")
                except Exception as e:
                    logger.error(f"Error extracting screenshots: {str(e)}")
                    #logger.exception(f"Exception details: {str(e)}")