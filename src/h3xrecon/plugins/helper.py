from typing import Dict, Any, List
import ipaddress
from h3xrecon.core.utils import is_valid_url, get_domain_from_url
from ipwhois import IPWhois
import requests
from loguru import logger
import aiohttp
import json
import random
import string

async def is_wildcard(subdomain):
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

            # Split the subdomain into parts
            parts = subdomain.split('.')
            pattern_tests = []

            # Test each position for potential wildcards
            for i in range(len(parts) - 1):  # -1 to avoid testing the TLD
                # Create a test subdomain with a random part at position i
                test_parts = parts.copy()
                random_label = ''.join(random.choices(string.ascii_lowercase, k=10))
                test_parts[i] = random_label
                test_subdomain = '.'.join(test_parts)
                pattern_tests.append(test_subdomain)

                # Create a second test to confirm the pattern
                test_parts[i] = ''.join(random.choices(string.ascii_lowercase, k=8))
                pattern_tests.append('.'.join(test_parts))

            # Test all generated patterns
            for test_subdomain in pattern_tests:
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

def fetch_aws_cidr():
    url = 'https://ip-ranges.amazonaws.com/ip-ranges.json'
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    ip_prefixes = [item['ip_prefix'] for item in data.get('prefixes', []) if 'ip_prefix' in item]
    return ip_prefixes


def fetch_ip_prefixes_by_service():
    try:
        # Fetch the JSON data
        url = 'https://ip-ranges.amazonaws.com/ip-ranges.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Group ip_prefix values by service
        grouped_prefixes = {}
        for item in data.get('prefixes', []):
            service = item.get('service', 'UNKNOWN').lower()
            if service == 'amazon':
                continue
                
            service_name = f"amazon_{service}"
            ip_prefix = item.get('ip_prefix')
            if service_name not in grouped_prefixes:
                grouped_prefixes[service_name] = {"cidr": [], "asn": []}
            if ip_prefix:
                grouped_prefixes[service_name]["cidr"].append(ip_prefix)
                grouped_prefixes[service_name]["asn"] = []
        return grouped_prefixes
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return {}

WAF_CDN_PROVIDERS = {
    'cloudflare': {
        'asn': ['13335'],
        'cidr': [
            '103.21.244.0/22',
            '103.22.200.0/22',
            '103.31.4.0/22',
            '104.16.0.0/13',
            '104.24.0.0/14',
            '108.162.192.0/18',
            '131.0.72.0/22',
            '141.101.64.0/18',
            '162.158.0.0/15',
            '172.64.0.0/13',
            '173.245.48.0/20',
            '188.114.96.0/20',
            '190.93.240.0/20',
            '197.234.240.0/22',
            '198.41.128.0/17'
        ]
    },
    'akamai': {
        'asn': ['12222', '16625', '16702', '17204', '18680', '18717', '20189', '20940', '21342', '21357', '21399', '22207', '22452', '23454', '23455', '23903', '24319', '26008', '30675', '31107', '31108', '31109', '31110', '31377', '33047', '33905', '34164', '34850', '35204', '35993', '35994', '36183', '39836', '43639', '55409', '55770', '63949', '133103', '393560'],
        'cidr': [
            '23.32.0.0/11',
            '23.192.0.0/11',
            '23.235.32.0/20',
            '104.156.80.0/20',
            '104.160.0.0/14',
            '104.192.0.0/14',
            '104.224.0.0/12',
            '104.248.0.0/13',
            '104.252.0.0/14',
            '104.252.16.0/20',
            '104.252.32.0/19',
            '104.252.64.0/18',
            '104.252.128.0/17'
        ]
    },
    'imperva': {
        'asn': [],
        'cidr': [
            '199.83.128.0/21',
            '198.143.32.0/19',
            '149.126.72.0/21',
            '103.28.248.0/22',
            '185.11.124.0/22',
            '192.230.64.0/18',
            '45.64.64.0/22',
            '107.154.0.0/16',
            '45.60.0.0/16',
            '45.223.0.0/16',
            '131.125.128.0/17'
        ]
    },
    'fastly': {
        'asn': ['54113'],
        'cidr': ["23.235.32.0/20","43.249.72.0/22","103.244.50.0/24","103.245.222.0/23","103.245.224.0/24","104.156.80.0/20","140.248.64.0/18","140.248.128.0/17","146.75.0.0/17","151.101.0.0/16","157.52.64.0/18","167.82.0.0/17","167.82.128.0/20","167.82.160.0/20","167.82.224.0/20","172.111.64.0/18","185.31.16.0/22","199.27.72.0/21","199.232.0.0/16"]
    },
    'f5': {
        'asn': [],
        'cidr': [
            '5.182.215.0/25',
            '84.54.61.0/25',
            '23.158.32.0/25',
            '84.54.62.0/25',
            '185.94.142.0/25',
            '185.94.143.0/25',
            '159.60.190.0/24',
            '159.60.168.0/24',
            '159.60.180.0/24',
            '159.60.174.0/24',
            '159.60.176.0/24',
            '5.182.213.0/25',
            '5.182.212.0/25',
            '5.182.213.128/25',
            '5.182.214.0/25',
            '84.54.60.0/25',
            '185.56.154.0/25',
            '159.60.160.0/24',
            '159.60.162.0/24',
            '159.60.188.0/24',
            '159.60.182.0/24',
            '159.60.178.0/24',
            '103.135.56.0/25',
            '103.135.57.0/25',
            '103.135.56.128/25',
            '103.135.59.0/25',
            '103.135.58.128/25',
            '103.135.58.0/25',
            '159.60.189.0/24',
            '159.60.166.0/24',
            '159.60.164.0/24',
            '159.60.170.0/24',
            '159.60.172.0/24',
            '159.60.191.0/24'
        ]
    },
    'edgecast': {
        'asn': ['15133'],
        'cidr': []
    },
    'edgenext': {
        'asn': ['139057','149981'],
        'cidr': []
    },
    'cloudfront': {
        'asn': ['14618', '16509'],
        'cidr': [
            '205.251.192.0/19',
            '204.246.164.0/22'
        ]
    },
    **fetch_ip_prefixes_by_service()
}

async def is_waf_cdn_ip(ip: str) -> Dict[str, Any]:
    """
    Check if an IP belongs to a WAF or CDN provider.
    
    Args:
        ip (str): IP address to check
        
    Returns:
        Dict with results containing:
        - is_waf_cdn (bool): True if IP belongs to WAF/CDN
        - provider (str): Name of the provider if found
        - match_type (str): Type of match (ASN or CIDR)
    """
    result = {
        "is_waf_cdn": False,
        "provider": None,
        "match_type": None
    }
    
    try:
        # Check against CIDR ranges
        ip_obj = ipaddress.ip_address(ip)
        for provider, info in WAF_CDN_PROVIDERS.items():
            for cidr in info['cidr']:
                if ip_obj in ipaddress.ip_network(cidr):
                    result["is_waf_cdn"] = True
                    result["provider"] = provider
                    result["match_type"] = "CIDR"
                    return result

        # Check ASN
        try:
            whois = IPWhois(ip)
            asn_data = whois.lookup_rdap(depth=1)
            asn = str(asn_data.get('asn', ''))
            
            for provider, info in WAF_CDN_PROVIDERS.items():
                if asn in info['asn']:
                    result["is_waf_cdn"] = True
                    result["provider"] = provider
                    result["match_type"] = "ASN"
                    return result
                
        except Exception as e:
            print(f"ASN lookup failed: {str(e)}")
            
    except Exception as e:
        print(f"Error checking IP {ip}: {str(e)}")
    
    return result