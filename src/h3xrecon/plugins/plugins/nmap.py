from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_service_data
from loguru import logger
import asyncio
import os
import xml.etree.ElementTree as ET

class NmapPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 300
    @property
    def target_types(self) -> List[str]:
        return ["ip", "domain"]


    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        cloud_provider = await db.get_cloud_provider(params.get("target", {}))
        if cloud_provider:
            logger.info(f"JOB SKIPPED: not running port scan for cloud provider {cloud_provider}")
            return
        
        logger.info(f"Scanning top 1000 ports on {params.get('target', {})}")
        command = f"nmap -p- --top-ports 1000 -oX /tmp/nmap_scan_{params.get('target', {})}.xml {params.get('target', {})} && cat /tmp/nmap_scan_{params.get('target', {})}.xml"
        
        process = None
        try:
            process = await self._create_subprocess_shell(command)
            
            try:
                while True:
                    try:
                        await asyncio.wait_for(process.wait(), timeout=0.1)
                        break  # Process completed
                    except asyncio.TimeoutError:
                        continue
                        
            except Exception as e:
                raise

            # Parse the XML output
            try:
                tree = ET.parse(f"/tmp/nmap_scan_{params.get('target', {})}.xml")
                root = tree.getroot()

                # Extract relevant information
                for port in root.findall('.//port'):
                    port_id = port.get('portid')
                    protocol = port.get('protocol')
                    state = port.find('state').get('state')
                    service = port.find('service')
                    service_name = service.get('name') if service is not None else None

                    yield {
                        "ip": params.get("target", {}),
                        "port": port_id,
                        "protocol": protocol,
                        "state": state,
                        "service": service_name
                    }

            except Exception as e:
                logger.error(f"Error parsing nmap output: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Error during {self.name} execution: {str(e)}")
            if process:
                process.kill()
            raise

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        service = output_msg.get("data", [])
        if service:
            await send_service_data(qm=qm, 
                                    data={
                                        "ip": service.get('ip'),
                                        "port": int(service.get('port')),
                                        "protocol": service.get('protocol'),
                                        "program_id": output_msg.get('program_id')
                                    }, 
                                    program_id=output_msg.get('program_id'),
                                    execution_id=output_msg.get('execution_id', ""),
                                    trigger_new_jobs=output_msg.get('trigger_new_jobs', True))