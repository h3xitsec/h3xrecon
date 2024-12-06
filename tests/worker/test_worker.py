import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch
from h3xrecon.worker.worker import Worker
from h3xrecon.core import Config

@pytest.fixture
def mock_config():
    config = Mock(spec=Config)
    config.redis = Mock(host='localhost', port=6379, db=0, password=None)
    config.nats = Mock()
    return config

@pytest.fixture
async def worker(mock_config):
    worker = Worker(mock_config)
    worker.function_executor = Mock()
    worker.function_executor.execute_function = AsyncMock()
    worker.function_executor.function_map = {"resolve_domain": Mock()}
    worker.redis_client = Mock()
    worker.db = Mock()
    worker.db.get_program_name = AsyncMock(return_value="test_program")
    return worker

@pytest.mark.asyncio
async def test_message_handler_normal_valid_execution(worker):
    # Arrange
    test_msg = {
        "function": "resolve_domain",
        "params": {"target": "example.com"},
        "program_id": 1,
        "force": False
    }
    
    worker.should_execute = AsyncMock(return_value=True)
    
    # Track if generator was called
    generator_called = False
    
    class AsyncGenMock:
        async def __call__(self, *args, **kwargs):
            nonlocal generator_called
            generator_called = True
            yield {"result": "success"}
    
    worker.function_executor.execute_function = AsyncGenMock()
    
    # Act
    await worker.message_handler(test_msg)
    
    # Assert
    assert generator_called, "Function executor should have been called"
    assert worker.should_execute.called, "should_execute should have been called"

@pytest.mark.asyncio
async def test_message_handler_skips_execution_when_should_execute_false(worker):
    # Arrange
    test_msg = {
        "function": "resolve_domain",
        "params": {"target": "example.com"},
        "program_id": 1,
        "force": False
    }
    
    worker.should_execute = AsyncMock(return_value=False)

    # Act
    await worker.message_handler(test_msg)

    # Assert
    worker.function_executor.execute_function.assert_not_called()

@pytest.mark.asyncio
async def test_message_handler_force_execution(worker):
    # Arrange
    test_msg = {
        "function": "resolve_domain",
        "params": {"target": "example.com"},
        "program_id": 1,
        "execution_id": "test_execution_id",
        "force": True
    }
    
    worker.should_execute = AsyncMock(return_value=False)
    
    # Track if generator was called
    generator_called = False
    
    class AsyncGenMock:
        async def __call__(self, *args, **kwargs):
            nonlocal generator_called
            generator_called = True
            yield {"result": "success"}
    
    worker.function_executor.execute_function = AsyncGenMock()

    # Act
    await worker.message_handler(test_msg)

    # Assert
    worker.should_execute.assert_not_called()
    assert generator_called, "Function executor should have been called even with force=True"

@pytest.mark.asyncio
async def test_message_handler_handles_execution_error(worker):
    # Arrange
    test_msg = {
        "function": "resolve_domain",
        "params": {"target": "example.com"},
        "program_id": 1,
        "force": False
    }
    
    worker.should_execute = AsyncMock(return_value=True)
    
    error_message = "Test error"
    
    # Create an async generator that raises an exception
    async def error_generator(*args, **kwargs):
        if False:  # This ensures it's treated as an async generator
            yield
        raise Exception(error_message)
    
    worker.function_executor.execute_function = error_generator

    # Act & Assert
    # The message handler should handle the error without raising it
    try:
        await worker.message_handler(test_msg)
    except Exception as e:
        pytest.fail(f"message_handler should handle exceptions, but raised: {str(e)}")