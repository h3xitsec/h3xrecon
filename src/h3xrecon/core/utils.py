import functools
from loguru import logger
import asyncio
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
from redis import Redis
from urllib.parse import urlparse
import ipaddress
import requests
import os
from ipwhois import IPWhois

def get_domain_from_url(url: str) -> str:
    try:
        if is_valid_hostname(url):
            return url
        _parsed_url = parse_url(url)
        return _parsed_url.get('website', {}).get('host', None)
    except Exception as e:
        logger.error(f"Error parsing URL {url}: {str(e)}")
        raise

def is_valid_hostname(hostname: str) -> bool:
    # Check if target contains any URL components
    if any(x in hostname for x in ["://", ":", "/", "?"]):
        return False
    # Check if target is a valid hostname format
    if not hostname or " " in hostname:
        return False
    # Basic hostname validation - at least one dot, valid chars
    if "." not in hostname or not all(c.isalnum() or c in "-._" for c in hostname):
        return False
    # Check parts between dots are valid
    parts = hostname.split(".")
    if not all(part and not (part.startswith("-") or part.endswith("-")) for part in parts):
        return False
    return True

def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def is_valid_cidr(cidr: str) -> bool:
    try:
        ipaddress.ip_network(cidr)
        return True
    except ValueError:
        return False

def is_valid_url(url: str) -> bool:
    try:
        if parse_url(url):
            return True
        return False
    except Exception as e:
        return False

def parse_url(url: str):
    _return = {}
    try:
        _parsed_url = urlparse(url)
        if _parsed_url.scheme is None or _parsed_url.hostname is None:
            raise Exception("Invalid URL")
        _port = None
        if _parsed_url.port:
            _port = _parsed_url.port
        else:
            if _parsed_url.scheme == 'https':
                _port = 443
            elif _parsed_url.scheme == 'http': 
                _port = 80
        _base_url = f"{_parsed_url.scheme}://{_parsed_url.hostname}:{_port}"
    except Exception as e:
        return False
    
    try:
        if _parsed_url.path:
            _path = _parsed_url.path
        else:
            _path = "/"
        _fixed_url = f"{_base_url}{_path}"
        _parsed_fixed_url = urlparse(_fixed_url)
    except Exception as e:
        logger.error(f"Error fixing url {url}: {str(e)}")
        return False
    
    _return['website'] = {
        "url": _base_url,
        "host": _parsed_fixed_url.hostname,
        "port": _parsed_fixed_url.port,
        "scheme": _parsed_fixed_url.scheme,
    }
    _return['website_path'] = {
        "url": _fixed_url,
        "path": _parsed_fixed_url.path,
    }
    return _return


def check_last_execution(function_name: str, params: Dict[str, Any], redis_cache: Redis) -> timedelta:
    """
    Check the last execution date/time of a function against the cache redis server
    Return the time since the last execution
    """
    try:
        # Handle extra_params specially if it exists as a list
        if 'extra_params' in params and isinstance(params['extra_params'], list):
            extra_params_str = f"extra_params={sorted(params['extra_params'])}"
        else:
            # Create a sorted, filtered copy of params excluding certain keys
            extra_params = []
            # Convert extra_params to a string representation
            extra_params_str = f'extra_params={extra_params}'

        # Construct Redis key
        if params.get('mode', None):
            redis_key = f"{function_name}:{params.get('target', 'unknown')}:{params.get('mode')}:{extra_params_str}"
        else:
            redis_key = f"{function_name}:{params.get('target', 'unknown')}:{extra_params_str}"
        logger.debug(f"Redis key: {redis_key}")
        # Get last execution time from Redis
        last_execution_time = redis_cache.get(redis_key)
        if not last_execution_time:
            return

        # Parse the timestamp and ensure it's timezone-aware
        last_execution_time = datetime.fromisoformat(last_execution_time.decode().replace('Z', '+00:00'))
        if last_execution_time.tzinfo is None:
            last_execution_time = last_execution_time.replace(tzinfo=timezone.utc)
        
        current_time = datetime.now(timezone.utc)
        time_since_last = current_time - last_execution_time
        return time_since_last

    except Exception as e:
        logger.error(f"Error checking execution history: {e}")
        # If there's an error checking history, allow execution
        raise e

def _truncate_value(value, max_length=200):
    """
    Truncate a value to a maximum length for logging purposes.
    Handles nested dictionaries and maintains key-value relationships.
    """
    if isinstance(value, dict):
        return {k: _truncate_value(v, max_length) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [_truncate_value(item, max_length) for item in value]
    
    str_value = str(value)
    if len(str_value) > max_length:
        half_length = (max_length - 3) // 2
        return f"{str_value[:half_length]}...{str_value[-half_length:]}"
    return str_value

def _truncate_args_kwargs(args, kwargs, max_length=200):
    """Truncate both args and kwargs for logging while preserving structure."""
    truncated_args = [_truncate_value(arg, max_length) for arg in args]
    truncated_kwargs = {k: _truncate_value(v, max_length) for k, v in kwargs.items()}
    return truncated_args, truncated_kwargs

def debug_trace(func):
    """
    A decorator that logs function entry and exit for both sync and async functions.
    Also logs the function parameters and return value with truncation for long values.
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        func_name = func.__qualname__
        trunc_args, trunc_kwargs = _truncate_args_kwargs(args, kwargs)
        logger.debug(f"Entering {func_name} with args={trunc_args}, kwargs={trunc_kwargs}")
        try:
            result = func(*args, **kwargs)
            trunc_result = _truncate_value(result)
            logger.debug(f"Exiting {func_name} with result={trunc_result}")
            return result
        except Exception as e:
            logger.debug(f"Exception in {func_name}: {str(e)}")
            raise

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = func.__qualname__
        trunc_args, trunc_kwargs = _truncate_args_kwargs(args, kwargs)
        #logger.debug(f"Entering {func_name} with args={trunc_args}, kwargs={trunc_kwargs}")
        try:
            result = await func(*args, **kwargs)
            #trunc_result = _truncate_value(result)
            #logger.debug(f"Exiting {func_name} with result={trunc_result}")
            return result
        except Exception as e:
            logger.debug(f"Exception in {func_name}: {str(e)}")
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper

def fetch_aws_cidr():
    url = 'https://ip-ranges.amazonaws.com/ip-ranges.json'
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    ip_prefixes = [item['ip_prefix'] for item in data.get('prefixes', []) if 'ip_prefix' in item]
    return ip_prefixes


def fetch_oci_cidr():
    try:
        url = 'https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Initialize the result structure
        result = {
            "oracle_cloud": {
                "cidr": []
            }
        }
        
        # Extract all CIDR ranges from all regions
        for region in data.get('regions', []):
            for cidr_obj in region.get('cidrs', []):
                if 'cidr' in cidr_obj:
                    result['oracle_cloud']['cidr'].append(cidr_obj['cidr'])
        
        return result
    except requests.RequestException as e:
        print(f"Error fetching OCI data: {e}")
        return {"oracle_cloud": {"cidr": []}}

def fetch_google_cloud_cidr():
    try:
        url = 'https://www.gstatic.com/ipranges/cloud.json'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Initialize the result structure
        grouped_prefixes = {}
        
        # Process all prefixes
        for prefix in data.get('prefixes', []):
            service = prefix.get('service', '').lower().replace(' ', '_')
            
            # Skip if no service defined
            if not service:
                continue
                
            # Initialize service entry if not exists
            if service not in grouped_prefixes:
                grouped_prefixes[service] = {"cidr": [], "asn": []}
            
            # Add IPv4 prefix if present
            if 'ipv4Prefix' in prefix:
                grouped_prefixes[service]["cidr"].append(prefix['ipv4Prefix'])
                    
        return grouped_prefixes
    except requests.RequestException as e:
        print(f"Error fetching Google Cloud data: {e}")
        return {}

def fetch_aws_cidr():
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
    'azure': {
        'asn': [],
        'cidr': open(os.path.join(os.path.dirname(__file__), 'wafcdn_ipranges/azure.txt')).read().splitlines()
    },
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
    **fetch_aws_cidr(),
    **fetch_oci_cidr(),
    **fetch_google_cloud_cidr()
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
            # First check CIDR ranges as they're faster to check
            for cidr in info['cidr']:
                try:
                    if ip_obj in ipaddress.ip_network(cidr):
                        result["is_waf_cdn"] = True
                        result["provider"] = provider
                        result["match_type"] = "CIDR"
                        return result
                except ValueError:
                    continue  # Skip invalid CIDR ranges
            
            # DISABLED ASN LOOKUP FOR NOW
            # Then check ASN if CIDR didn't match
            # if info['asn']:
            #     whois = IPWhois(ip)
            #     try:
            #         asn_data = whois.lookup_rdap(depth=1)
            #         asn = str(asn_data.get('asn', None))
            #         if asn and asn in info['asn']:
            #             result["is_waf_cdn"] = True
            #             result["provider"] = provider
            #             result["match_type"] = "ASN"
            #             return result
            #     except Exception as e:
            #         logger.debug(f"ASN lookup failed for IP {ip}: {str(e)}")
            #         logger.exception(e)
            #         continue
            
    except Exception as e:
        logger.error(f"Error checking WAF/CDN IP {ip}: {str(e)}")
    
    return result