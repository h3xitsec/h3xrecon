from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from loguru import logger
import asyncio
import os
class FindSubdomainsCTFR(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} on {params.get('target', {})}")
        command = f"python /opt/ctfr/ctfr.py -d {params.get('target', {})} -o /tmp/ctfr.log > /dev/null 2>&1 && cat /tmp/ctfr.log | grep -Ev '.*\\*.*' | sort -u && rm /tmp/ctfr.log"
        
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
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.1)
                        if not line:
                            break
                        
                        output = line.decode().strip()
                        if output:
                            yield {"subdomain": [output]}
                            
                    except asyncio.TimeoutError:
                        continue
                        
            except Exception as e:
                raise
                
            await process.wait()
                
        except Exception as e:
            logger.error(f"Error during {self.name} execution: {str(e)}")
            if process:
                process.kill()
            raise
    
    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        domain_msg = {
            "program_id": output_msg.get('program_id'),
            "data_type": "domain",
            "in_scope": output_msg.get('in_scope'),
            "data": output_msg.get('output', {}).get('subdomain')
        }
        await qm.publish_message(subject="data.input", stream="DATA_INPUT", message=domain_msg)