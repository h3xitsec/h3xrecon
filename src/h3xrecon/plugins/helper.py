from typing import Dict, Any

async def send_nuclei_data(qm, data: str, program_id: int):
    
    msg = {
        "program_id": program_id,
        "data_type": "nuclei",
        "data": [data]
    }
    await qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_domain_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None):
    
    msg = {
        "program_id": program_id,
        "data_type": "domain",
        "data": [data],
        "attributes": attributes
    }
    await qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_ip_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None):
    
    msg = {
        "program_id": program_id,
        "data_type": "ip",
        "data": [data],
        "attributes": attributes
    }
    await qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_service_data(qm, data: str, program_id: int):

    msg = {
        "program_id": program_id,
        "data_type": "service",
        "data": [data]
    }
    await qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_url_data(qm, data: str, program_id: int):
    
    msg = {
        "program_id": program_id,
        "data_type": "url",
        "data": [data]
    }
    await qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)

async def send_certificate_data(qm, data: str, program_id: int):
    
    msg = {
        "program_id": program_id,
        "data_type": "certificate",
        "data": [data]
    }
    await qm.publish_message(subject="recon.data", stream="RECON_DATA", message=msg)