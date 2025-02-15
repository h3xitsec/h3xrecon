from typing import Dict, Any, List
import ipaddress
from h3xrecon.core.utils import is_valid_url, get_domain_from_url
from loguru import logger
import aiohttp
import json
import random
import string
import os

async def is_wildcard(subdomain: str):
    RECORD_TYPE_CODES = {
        "A": 1,
        "AAAA": 28,
        "TXT": 16,
        "NS": 2,
        "CNAME": 5,
        "MX": 15
    }
    DNS_API_URL = "https://cloudflare-dns.com/dns-query"
    async def query_dns_records(session,subdomain, record_type):
            try:
                async with session.get(DNS_API_URL, params={'name': subdomain, 'type': record_type}, headers={'Accept': 'application/dns-json'}) as response:
                    if response.status == 200:
                        raw_response = await response.text()
                        try:
                            result = json.loads(raw_response)
                            has_answer = "Answer" in result
                            answers = result.get("Answer", []) if has_answer else []
                            # Look at the first answer's type, as this represents the actual record type
                            # before any CNAME resolution
                            if answers:
                                first_answer_type = answers[0].get("type")
                                # Convert type code back to string for easier comparison
                                first_record_type = next(
                                    (rtype for rtype, code in RECORD_TYPE_CODES.items()
                                        if code == first_answer_type), None
                                )
                                return bool(answers), answers, first_record_type

                            if not has_answer and "Authority" in result:
                                return False, [], None

                            return bool(answers), answers, None
                        except json.JSONDecodeError as e:
                            return False, [], None
            except Exception as e:
                return False, [], None

    async def wildcard_check(session, subdomain, record_type):
        try:
            record_type_code = RECORD_TYPE_CODES.get(record_type.upper())
            if not record_type_code:
                return False, None

            valid_base, base_answers, base_actual_type = await query_dns_records(session, subdomain, record_type)
            if not valid_base or not base_answers:
                return False, None

            random_label = ''.join(random.choices(string.ascii_lowercase, k=10))
            test_patterns = []
            test_patterns.append(f"{random_label}.{subdomain}")
            # Test all generated patterns
            for test_subdomain in test_patterns:
                valid_garbage, garbage_answers, garbage_actual_type = await query_dns_records(
                    session, test_subdomain, record_type
                )
                
                # If any test succeeds with the same record type, it's a wildcard
                if valid_garbage and base_actual_type == garbage_actual_type:
                    return True, base_actual_type

            return False, None

        except Exception as e:
            print(f"[!] Error during wildcard check: {str(e)}")
            return False, None

    async def process_subdomain(subdomain):
        async with aiohttp.ClientSession() as session:
            record_types = ["A", "AAAA", "NS", "CNAME", "TXT", "MX"]
            try:
                for record_type in record_types:
                    has_records, _, actual_type = await query_dns_records(session, subdomain, record_type)
                    if has_records:
                        is_wildcard, wildcard_type = await wildcard_check(session, subdomain, record_type)
                        if is_wildcard:
                            return (True, f"wildcard_{wildcard_type}")
                        else:
                            return (False, None)
                return (False, "no_records")
            except Exception as e:
                logger.exception(f"Error processing subdomain {subdomain}: {e}")
                return (False, "error")
    
    return await process_subdomain(subdomain)


def unclutter_url_list(url_list: List[str]) -> List[str]:
    """Remove parameters and hashes from URLs and return unique cleaned URLs.
    
    Args:
        url_list: List of URLs to process
        
    Returns:
        List of unique URLs in format scheme://hostname:port/path
    """
    cleaned_urls = set()
    for url in url_list:
        if not url:
            continue
        # Split on ? to remove parameters and # to remove hash
        base_url = url.split('?')[0].split('#')[0]
        # Ensure we have at least scheme and host
        if '://' in base_url:
            cleaned_urls.add(base_url)
    return list(cleaned_urls)

def log_sent_data(func):
    async def wrapper(qm, data: str, program_id: int, *args, **kwargs):
        # Extract data_type from function name
        if data:
            data_type = func.__name__.replace('send_', '').replace('_data', '')
            if data_type == "domain":
                if is_valid_url(data):
                    data = get_domain_from_url(data)
            # Build message
            msg = {
                "program_id": program_id,
                "data_type": data_type,
                "data": [data],
                "trigger_new_jobs": kwargs.get('trigger_new_jobs', True),
                "execution_id": kwargs.get('execution_id', None),
                "response_id": kwargs.get('response_id', None)
            }
            
            # Add attributes if provided
            if kwargs.get('attributes'):
                msg["attributes"] = kwargs['attributes']
            # Publish message
            await qm.publish_message(subject="data.input", stream="DATA_INPUT", message=msg)
            logger.info(f"SENT RECON DATA: {data_type} : {msg} : {msg.get('attributes', "No Attributes")}")
            #return msg
    return wrapper

@log_sent_data
async def send_dns_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_nuclei_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_domain_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_ip_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_service_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_website_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_website_path_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_certificate_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

@log_sent_data
async def send_screenshot_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None, execution_id: str = None, trigger_new_jobs: bool = True):
    pass

def parse_dns_record(record_line: str) -> dict:
    """Parse a single DNS record line and return structured data."""
    # Skip PSEUDOSECTION lines and empty lines
    if record_line.startswith(';') or record_line.startswith('\n') or not record_line.strip():
        return None
    
    try:
        # Split the record line into components
        parts = record_line.strip().split('\t')
        # Remove empty strings from parts
        parts = [p for p in parts if p]
        
        if len(parts) < 5:
            return None
            
        # Extract components
        hostname = parts[0].rstrip('.')  # Remove trailing dot
        ttl = int(parts[1])
        record_class = parts[2]
        record_type = parts[3]
        value = parts[4]
        
        return {
            "hostname": hostname,
            "ttl": ttl,
            "dns_class": record_class,
            "dns_type": record_type,
            "value": value
        }
    except (IndexError, ValueError):
        return None