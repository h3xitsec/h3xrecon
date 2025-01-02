import functools
from loguru import logger
import asyncio

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