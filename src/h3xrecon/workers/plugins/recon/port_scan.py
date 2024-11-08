from typing import AsyncGenerator, Dict, Any
from h3xrecon.workers.plugins.base import ReconPlugin
from loguru import logger
import asyncio
import os
import xml.etree.ElementTree as ET

class PortScan(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Scanning top 1000 ports on {target}")
        command = f"""
            #!/bin/bash
            nmap -p- --top-ports 1000 -oX /tmp/nmap_scan_{target}.xml {target}
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )

        await process.wait()

        # Parse the XML output
        tree = ET.parse(f"/tmp/nmap_scan_{target}.xml")
        root = tree.getroot()

        # Extract relevant information
        for port in root.findall('.//port'):
            port_id = port.get('portid')
            protocol = port.get('protocol')
            state = port.find('state').get('state')
            service = port.find('service')
            service_name = service.get('name') if service is not None else None

            yield [{
                "ip": target,
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