from h3xrecon.core import Config
from h3xrecon.core import QueueManager
from typing import Dict, Any
config = Config()
helper_qm = QueueManager(config.nats)

async def send_nuclei_data(data: str, program_id: int):
    
    msg = {
        "program_id": program_id,
        "data_type": "nuclei",
        "data": [data]
    }
    await helper_qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_domain_data(data: str, program_id: int, attributes: Dict[str, Any] = None):
    
    msg = {
        "program_id": program_id,
        "data_type": "domain",
        "data": [data],
        "attributes": attributes
    }
    await helper_qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_ip_data(data: str, program_id: int):
    
    msg = {
        "program_id": program_id,
        "data_type": "ip",
        "data": [data]
    }
    await helper_qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_service_data(data: str, program_id: int):

    msg = {
        "program_id": program_id,
        "data_type": "service",
        "data": [data]
    }
    await helper_qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_url_data(data: str, program_id: int):
    
    msg = {
        "program_id": program_id,
        "data_type": "url",
        "data": [data]
    }
    await helper_qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_certificate_data(data: str, program_id: int):
    
    msg = {
        "program_id": program_id,
        "data_type": "certificate",
        "data": [data]
    }
    await helper_qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)