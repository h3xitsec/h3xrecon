from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_ip_data, send_domain_data, is_waf_cdn_ip, WAF_CDN_PROVIDERS
from loguru import logger
import asyncio
import os
import json

class ReverseResolveIP(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get('target', {})}")
        command = f"echo \"{params.get('target', {})}\" | ~/.pdtm/go/bin/dnsx -silent -nc -ptr -resp -j|jq -cr '.ptr[]'"
        
        process = None
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            
            try:
                while True:
                    try:
                        # Check if the task is being cancelled
                        if asyncio.current_task().cancelled():
                            logger.info(f"Task cancelled, terminating {self.name}")
                            if process:
                                process.terminate()
                                try:
                                    await asyncio.wait_for(process.wait(), timeout=5.0)
                                except asyncio.TimeoutError:
                                    process.kill()
                            return
                            
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.1)
                        if not line:
                            break
                        logger.debug(f"Received line: {line.decode()}")
                        try:
                            yield {"domain": line.decode().strip().strip('"')}
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse JSON output: {e}")
                            
                    except asyncio.TimeoutError:
                        continue
                        
            except asyncio.CancelledError:
                logger.info(f"Task cancelled, terminating {self.name}")
                if process:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        process.kill()
                raise
                
            await process.wait()
                
        except Exception as e:
            logger.error(f"Error during {self.name} execution: {str(e)}")
            if process:
                process.kill()
            raise
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        logger.debug(WAF_CDN_PROVIDERS.keys())
        wafcdn_result = await is_waf_cdn_ip(output_msg.get('source', []).get('params', {}).get('target'))
        if wafcdn_result.get('is_waf_cdn'):
            cloud_provider = wafcdn_result.get('provider')
        else:
            cloud_provider = None
        ip_data = output_msg.get('source', []).get('params', {}).get('target')
        ip_attributes = {
            "ptr": output_msg.get('output', []).get('domain'),
            "cloud_provider": cloud_provider
        }
        await send_domain_data(qm=qm, data=output_msg.get('output', []).get('domain'), program_id=output_msg.get('program_id'))
        await send_ip_data(qm=qm, data=ip_data, program_id=output_msg.get('program_id'), attributes=ip_attributes)