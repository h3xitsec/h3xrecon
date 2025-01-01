from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_screenshot_data, send_url_data
from loguru import logger
import asyncio
import json
import os
import base64
import tarfile
import tempfile
import re
import shutil
from os.path import basename

SCREENSHOT_BASE_STORAGE_PATH = "/app/screenshots"

class Screenshot(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

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
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            
            # Read the entire output at once instead of line by line
            stdout, stderr = await process.communicate()
            
            if stdout:
                # Yield the entire base64 encoded data
                yield {"data": stdout.decode().strip()}
            
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
        SCREENSHOT_STORAGE_PATH = os.path.join(SCREENSHOT_BASE_STORAGE_PATH, str(output_msg.get('program_id', {})))
        if not os.path.exists(SCREENSHOT_STORAGE_PATH):
            os.makedirs(SCREENSHOT_STORAGE_PATH)
        base64_archive = output_msg.get('output', {}).get('data')
        if base64_archive:
            archive_data = base64.b64decode(base64_archive)
            with tempfile.TemporaryDirectory() as temp_dir:
                logger.debug(f"Extracting screenshots to {temp_dir}")
                os.makedirs(temp_dir, exist_ok=True)
                try:
                    with open(os.path.join(temp_dir, 'output_parser.tar.gz'), 'wb') as f:
                        f.write(archive_data)
                    with tarfile.open(os.path.join(temp_dir, 'output_parser.tar.gz'), 'r:gz') as tar:
                        tar.extractall(path=temp_dir)
                    os.remove(os.path.join(temp_dir, 'output_parser.tar.gz'))
                    screenshots = [file for file in os.listdir(temp_dir) if re.match(r'.*\.png', file)]
                    # Make sure the URL is sent to data worker
                    url_msg = {
                        "url": output_msg.get('source', {}).get('params', {}).get('target')
                    }
                    await send_url_data(qm, url_msg, output_msg.get('program_id', {}))
                    await asyncio.sleep(2)
                    logger.debug(f"Found {len(screenshots)} screenshots")
                    for file in screenshots:
                        logger.debug(f"Moving {file} to {SCREENSHOT_STORAGE_PATH}")
                        shutil.move(os.path.join(temp_dir, file), os.path.join(SCREENSHOT_STORAGE_PATH, file))
                        if file.endswith('.png'):
                            screenshot_msg = {
                                "url": output_msg.get('source', {}).get('params', {}).get('target'),
                                "path": os.path.join(SCREENSHOT_STORAGE_PATH, file),
                            }
                            await send_screenshot_data(qm, screenshot_msg, output_msg.get('program_id', ""))
                except Exception as e:
                    logger.error(f"Error extracting screenshots: {str(e)}")
