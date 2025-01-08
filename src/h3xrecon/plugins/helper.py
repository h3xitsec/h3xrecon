from typing import Dict, Any
import ipaddress
from h3xrecon.core.utils import is_valid_url, get_domain_from_url
from ipwhois import IPWhois
import requests
from loguru import logger
from urllib.parse import urlparse

def log_sent_data(func):
    async def wrapper(qm, data: str, program_id: int, *args, **kwargs):
        # Extract data_type from function name
        data_type = func.__name__.replace('send_', '').replace('_data', '')
        if data_type == "domain":
            if is_valid_url(data):
                data = get_domain_from_url(data)
        # Build message
        msg = {
            "program_id": program_id,
            "data_type": data_type,
            "data": [data]
        }
        
        # Add attributes if provided
        if kwargs.get('attributes'):
            msg["attributes"] = kwargs['attributes']
        
        # Publish message
        await qm.publish_message(subject="data.input", stream="DATA_INPUT", message=msg)
        logger.info(f"SENT JOB OUTPUT: {data_type} : {data}")
        return msg
    return wrapper


@log_sent_data
async def send_nuclei_data(qm, data: str, program_id: int):
    pass

@log_sent_data
async def send_domain_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None):
    pass

@log_sent_data
async def send_ip_data(qm, data: str, program_id: int, attributes: Dict[str, Any] = None):
    pass

@log_sent_data
async def send_service_data(qm, data: str, program_id: int):
    pass

@log_sent_data
async def send_website_data(qm, data: str, program_id: int):
    pass

@log_sent_data
async def send_website_path_data(qm, data: str, program_id: int):
    pass

@log_sent_data
async def send_certificate_data(qm, data: str, program_id: int):
    pass

@log_sent_data
async def send_screenshot_data(qm, data: str, program_id: int):
    pass

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