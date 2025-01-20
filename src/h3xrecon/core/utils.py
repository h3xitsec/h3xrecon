import functools
from loguru import logger
import asyncio
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
from redis import Redis
from urllib.parse import urlparse
import ipaddress

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
    if "." not in hostname or not all(c.isalnum() or c in "-." for c in hostname):
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
        logger.debug(f"Entering {func_name} with args={trunc_args}, kwargs={trunc_kwargs}")
        try:
            result = await func(*args, **kwargs)
            trunc_result = _truncate_value(result)
            logger.debug(f"Exiting {func_name} with result={trunc_result}")
            return result
        except Exception as e:
            logger.debug(f"Exception in {func_name}: {str(e)}")
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper 