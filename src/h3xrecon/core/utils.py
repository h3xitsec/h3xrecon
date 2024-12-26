import functools
import inspect
from loguru import logger
import asyncio

def debug_trace(func):
    """
    A decorator that logs function entry and exit for both sync and async functions.
    Also logs the function parameters and return value.
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        func_name = func.__qualname__
        logger.debug(f"Entering {func_name} with args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Exiting {func_name} with result={result}")
            return result
        except Exception as e:
            logger.debug(f"Exception in {func_name}: {str(e)}")
            raise

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = func.__qualname__
        logger.debug(f"Entering {func_name} with args={args}, kwargs={kwargs}")
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"Exiting {func_name} with result={result}")
            return result
        except Exception as e:
            logger.debug(f"Exception in {func_name}: {str(e)}")
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper 