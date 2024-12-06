from typing import AsyncGenerator, Dict, Any
from h3xrecon.core import *
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_service_data
from loguru import logger
import asyncio
import os
import xml.etree.ElementTree as ET

class PortScan(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Scanning top 1000 ports on {params.get("target", {})}")
        command = f"""
            #!/bin/bash
            nmap -p- --top-ports 1000 -oX /tmp/nmap_scan_{params.get("target", {})}.xml {params.get("target", {})}
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )

        await process.wait()

        # Parse the XML output
        tree = ET.parse(f"/tmp/nmap_scan_{params.get("target", {})}.xml")
        root = tree.getroot()

        # Extract relevant information
        for port in root.findall('.//port'):
            port_id = port.get('portid')
            protocol = port.get('protocol')
            state = port.find('state').get('state')
            service = port.find('service')
            service_name = service.get('name') if service is not None else None

            yield [{
                "ip": params.get("target", {}),
                "port": port_id,
                "protocol": protocol,
                "state": state,
                "service": service_name
            }]

        # Handle extraports if needed
        extraports = root.find('.//extraports')
        if extraports is not None:
            count = extraports.get('count')
            logger.info(f"Total filtered ports: {count}")
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        self.config = Config()
        self.qm = QueueManager(self.config.nats)
        for service in output_msg.get('output', []):
            await send_service_data(
                ip=service.get('ip'),
                port=int(service.get('port')),
                protocol=service.get('protocol'),
                program_id=output_msg.get('program_id')
            )