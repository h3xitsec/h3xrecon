from h3xrecon.plugins import ReconPlugin
import pytest
import asyncio
from typing import AsyncGenerator, Dict, Any

class TestPlugin(ReconPlugin):
    """Test implementation of ReconPlugin for testing base functionality"""
    @property
    def name(self) -> str:
        return "test_plugin"

    async def execute(self, params: dict) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"test": "data"}

@pytest.mark.asyncio
class TestReconPlugin:
    @pytest.fixture
    def plugin(self):
        """Fixture that provides a test plugin instance"""
        return TestPlugin()

    async def test_read_subprocess_output_success(self, plugin):
        # Create mock process
        class MockProcess:
            def __init__(self, test_data):
                self.test_data = test_data
                
            class MockStdout:
                def __init__(self, data_lines):
                    self.data_lines = data_lines
                    self.current_index = 0
                    
                async def readuntil(self, delimiter):
                    if self.current_index >= len(self.data_lines):
                        raise asyncio.exceptions.IncompleteReadError(b'', 0)
                    line = self.data_lines[self.current_index]
                    self.current_index += 1
                    return line
                    
            async def wait(self):
                return 0

        # Test data
        test_lines = [
            b'test line 1\n',
            b'test line 2\n',
            b'test line 3\n'
        ]
        
        mock_process = MockProcess(test_lines)
        mock_process.stdout = MockProcess.MockStdout(test_lines)
        
        outputs = []
        async for line in plugin._read_subprocess_output(mock_process):
            outputs.append(line)
            
        assert len(outputs) == 3
        assert outputs == ['test line 1', 'test line 2', 'test line 3']

    async def test_read_subprocess_output_incomplete_read(self, plugin):
        class MockProcess:
            class MockStdout:
                async def readuntil(self, delimiter):
                    raise asyncio.exceptions.IncompleteReadError(b'', 0)
                    
            async def wait(self):
                return 0
                
        mock_process = MockProcess()
        mock_process.stdout = MockProcess.MockStdout()
        
        outputs = []
        async for line in plugin._read_subprocess_output(mock_process):
            outputs.append(line)
            
        assert len(outputs) == 0

    async def test_read_subprocess_output_limit_overrun(self, plugin):
        class MockProcess:
            def __init__(self):
                self.read_count = 0
                
            class MockStdout:
                def __init__(self):
                    self.read_count = 0
                    
                async def readuntil(self, delimiter):
                    raise asyncio.exceptions.LimitOverrunError('dummy', 1024)
                    
                async def read(self, size):
                    return b'overflow data\n'
                    
            async def wait(self):
                return 0

        mock_process = MockProcess()
        mock_process.stdout = MockProcess.MockStdout()
        
        outputs = []
        async for line in plugin._read_subprocess_output(mock_process):
            outputs.append(line)
            break  # Break after first iteration to avoid infinite loop
            
        assert len(outputs) == 1
        assert outputs[0] == 'overflow data'

    @pytest.fixture(autouse=True)
    async def cleanup_tasks(self):
        yield
        # Clean up any pending tasks after each test
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass