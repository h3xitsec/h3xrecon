import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from h3xrecon.server.jobprocessor import JobProcessor, FunctionExecution
from h3xrecon.core import Config
import asyncio
from datetime import datetime
from uuid import uuid4
import importlib
from loguru import logger
import sys

class LogCapture:
    def __init__(self):
        self.messages = []

    def write(self, message):
        self.messages.append(message.strip())

    def clear(self):
        self.messages.clear()

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """Setup loguru logging to work with pytest caplog"""
    # Remove any existing handlers
    logger.remove()
    # Add a handler that writes to caplog
    logger.add(
        sys.stderr,
        format="{message}",
        level="DEBUG",
        catch=True,
    )
    yield
    # Cleanup after test
    logger.remove()

@pytest.fixture
def config():
    """Provides a test configuration instance"""
    return Config()

@pytest.fixture
def mock_dependencies(config):
    """Mocks the dependencies of JobProcessor"""
    with patch('h3xrecon.server.jobprocessor.DatabaseManager') as MockDBManager, \
         patch('h3xrecon.server.jobprocessor.QueueManager') as MockQueueManager, \
         patch('h3xrecon.server.jobprocessor.redis.Redis') as MockRedis:
        
        mock_db = MockDBManager.return_value
        mock_qm = MockQueueManager.return_value
        mock_redis = MockRedis.return_value
        
        # Mock the methods used in JobProcessor
        mock_db.log_or_update_function_execution = AsyncMock()
        mock_db.connect = AsyncMock()
        mock_qm.connect = AsyncMock()
        mock_qm.subscribe = AsyncMock()
        
        yield {
            'db': mock_db,
            'qm': mock_qm,
            'redis': mock_redis
        }

@pytest.fixture
def job_processor(config, mock_dependencies):
    """Provides a JobProcessor instance with mocked dependencies"""
    with patch('h3xrecon.server.jobprocessor.importlib.util.find_spec') as mock_find_spec, \
         patch('h3xrecon.server.jobprocessor.importlib.import_module') as mock_import:
        # Create a mock plugins module
        mock_plugins = MagicMock()
        mock_plugins.PLUGINS = {}  # Empty plugins dictionary
        mock_plugins.__path__ = ['/mock/path/to/plugins']  # Add mock __path__ attribute
        mock_plugins.__name__ = 'h3xrecon.plugins.plugins'  # Add mock __name__ attribute
        
        def import_side_effect(name, *args, **kwargs):
            if name == 'h3xrecon.plugins.plugins':
                return mock_plugins
            return importlib.import_module(name, *args, **kwargs)
        
        mock_import.side_effect = import_side_effect
        mock_find_spec.return_value = None
        
        job_processor = JobProcessor(config)
        # Set other dependencies
        job_processor.db = mock_dependencies['db']
        job_processor.queue_manager = mock_dependencies['qm']
        job_processor.redis = mock_dependencies['redis']
        return job_processor

@pytest.fixture
def log_capture():
    capture = LogCapture()
    logger.remove()  # Remove default handlers
    handler_id = logger.add(
        capture.write,
        format="{message}",
        level="ERROR",
        backtrace=True,
        diagnose=True
    )
    yield capture
    logger.remove(handler_id)  # Clean up specific handler

@pytest.mark.asyncio
class TestJobProcessor:

    async def test_message_handler_valid_message(self, job_processor, mock_dependencies):
        """Test that a valid message is processed correctly"""
        valid_message = {
            "execution_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "source": {
                "function": "test_function",
                "params": {
                    "function": "test_function",
                    "target": "test_target"
                }
            },
            "program_id": "123",
            "data": [{"key": "value"}],
            "nolog": False
        }
        
        with patch.object(job_processor, 'process_function_output', AsyncMock()) as mock_process_output:
            await job_processor.message_handler(valid_message)
            
            # Check that log_or_update_function_execution was called with correct parameters
            mock_dependencies['db'].log_or_update_function_execution.assert_awaited_once()
            args, kwargs = mock_dependencies['db'].log_or_update_function_execution.call_args
            assert args[0]['execution_id'] == valid_message['execution_id']
            assert args[0]['timestamp'] == valid_message['timestamp']
            assert args[0]['function_name'] == valid_message['source']['params']['function']
            assert args[0]['target'] == valid_message['source']['params']['target']
            assert args[0]['program_id'] == valid_message['program_id']
            assert args[0]['results'] == valid_message['data']
            
            # Check that Redis was updated correctly
            redis_key = f"{valid_message['source']['function']}:{valid_message['source']['params']['target']}"
            mock_dependencies['redis'].set.assert_called_once_with(redis_key, valid_message['timestamp'])
            
            # Check that process_function_output was called
            mock_process_output.assert_awaited_once_with(valid_message)

    async def test_message_handler_invalid_execution_id(self, job_processor, mock_dependencies, log_capture):
        """Test that an invalid execution_id is handled correctly"""
        invalid_message = {
            "execution_id": "invalid-uuid",
            "timestamp": datetime.utcnow().isoformat(),
            "source": {
                "function": "test_function",
                "params": {
                    "function": "test_function",
                    "target": "test_target"
                }
            },
            "program_id": "123",
            "data": [{"key": "value"}],
            "nolog": False
        }
        
        await job_processor.message_handler(invalid_message)
        
        # Check that an error was logged
        assert any(
            "ValueError: execution_id must be a valid UUID" in message
            for message in log_capture.messages
        ), f"Expected error message not found in captured messages: {log_capture.messages}"
        
        # Ensure that log_or_update_function_execution and process_function_output were not called
        mock_dependencies['db'].log_or_update_function_execution.assert_not_called()
        mock_dependencies['qm'].process_function_output.assert_not_called()

    async def test_message_handler_invalid_timestamp(self, job_processor, mock_dependencies, log_capture):
        """Test that an invalid timestamp is handled correctly"""
        invalid_message = {
            "execution_id": str(uuid4()),
            "timestamp": "invalid-timestamp",
            "source": {
                "function": "test_function",
                "params": {
                    "function": "test_function",
                    "target": "test_target"
                }
            },
            "program_id": "123",
            "data": [{"key": "value"}],
            "nolog": False
        }
        
        await job_processor.message_handler(invalid_message)
        
        # Check that an error was logged
        assert any(
            "ValueError: timestamp must be a valid ISO format timestamp" in message
            for message in log_capture.messages
        ), f"Expected error message not found in captured messages: {log_capture.messages}"
        
        # Ensure that log_or_update_function_execution and process_function_output were not called
        mock_dependencies['db'].log_or_update_function_execution.assert_not_called()
        mock_dependencies['qm'].process_function_output.assert_not_called()

    async def test_message_handler_invalid_program_id(self, job_processor, mock_dependencies, log_capture):
        """Test that an invalid program_id is handled correctly"""
        invalid_message = {
            "execution_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "source": {
                "function": "test_function",
                "params": {
                    "function": "test_function",
                    "target": "test_target"
                }
            },
            "program_id": "invalid_int",
            "data": [{"key": "value"}],
            "nolog": False
        }
        
        await job_processor.message_handler(invalid_message)
        
        # Check that an error was logged
        assert any(
            "ValueError: program_id must be an integer" in message
            for message in log_capture.messages
        ), f"Expected error message not found in captured messages: {log_capture.messages}"
        
        # Ensure that log_or_update_function_execution and process_function_output were not called
        mock_dependencies['db'].log_or_update_function_execution.assert_not_called()
        mock_dependencies['qm'].process_function_output.assert_not_called()

    async def test_message_handler_missing_fields(self, job_processor, mock_dependencies, log_capture):
        """Test that messages with missing fields are handled correctly"""
        invalid_message = {
            # Missing 'execution_id'
            "timestamp": datetime.utcnow().isoformat(),
            "source": {
                "function": "test_function",
                "params": {
                    "function": "test_function",
                    "target": "test_target"
                }
            },
            "program_id": "123",
            "data": [{"key": "value"}],
            "nolog": False
        }
        
        await job_processor.message_handler(invalid_message)
        
        # Check that a KeyError was logged
        assert any(
            "KeyError" in message
            for message in log_capture.messages
        ), f"Expected error message not found in captured messages: {log_capture.messages}"
        
        # Ensure that log_or_update_function_execution and process_function_output were not called
        mock_dependencies['db'].log_or_update_function_execution.assert_not_called()
        mock_dependencies['qm'].process_function_output.assert_not_called()

    async def test_message_handler_invalid_types(self, job_processor, mock_dependencies, log_capture):
        """Test that messages with invalid field types are handled correctly"""
        invalid_message = {
            "execution_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "should_be_a_dict",  # Invalid type
            "program_id": "123",
            "data": "should_be_a_list",
            "nolog": False
        }
        
        await job_processor.message_handler(invalid_message)
        
        # Print captured messages for debugging
        print("Captured messages:", log_capture.messages)
        
        # Check for the error message
        assert any(
            "TypeError: source must be a dictionary" in message
            for message in log_capture.messages
        ), f"Expected error message not found in captured messages: {log_capture.messages}"
        
        # Ensure that log_or_update_function_execution and process_function_output were not called
        mock_dependencies['db'].log_or_update_function_execution.assert_not_called()
        mock_dependencies['qm'].process_function_output.assert_not_called()

    async def test_message_handler_exceptions(self, job_processor, mock_dependencies):
        """Test that exceptions in processing are handled and logged"""
        valid_message = {
            "execution_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "source": {
                "function": "test_function",
                "params": {
                    "function": "test_function",
                    "target": "test_target"
                }
            },
            "program_id": 123,
            "data": [{"key": "value"}],
            "nolog": False
        }
        
        # Configure log_or_update_function_execution to raise an exception
        mock_dependencies['db'].log_or_update_function_execution.side_effect = Exception("Database failure")
        
        with patch('h3xrecon.server.jobprocessor.logger') as mock_logger:
            await job_processor.message_handler(valid_message)
            
            # Check that the error was logged
            mock_logger.error.assert_called_with(
                "Error logging or updating function execution: Database failure"
            )