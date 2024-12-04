import pytest
import json
from h3xrecon.plugins.plugins.reverse_resolve_ip import ReverseResolveIP
import asyncio

@pytest.mark.asyncio
class TestReverseResolveIPPlugin:
    @pytest.fixture(autouse=True)
    async def setup_teardown(self):
        """Setup and teardown for each test"""
        yield
        # Cleanup after each test
        tasks = [t for t in asyncio.all_tasks() 
                if t is not asyncio.current_task() 
                and not t.done()]
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.fixture
    def reverse_resolve_ip_plugin(self):
        """Fixture that provides a ReverseResolveIP plugin instance"""
        return ReverseResolveIP()

    async def test_read_subprocess_output(self, reverse_resolve_ip_plugin, mock_process_factory, sample_reverse_resolve_ip_output):
        # Create test data
        test_data = [
            (json.dumps(sample_reverse_resolve_ip_output) + '\n').encode()
        ]
        
        # Create mock process using the factory
        mock_process = mock_process_factory(test_data)
        
        # Test the output processing
        outputs = []
        async for line in reverse_resolve_ip_plugin._read_subprocess_output(mock_process):
            outputs.append(line)
            
        assert len(outputs) == 1
        parsed_output = json.loads(outputs[0])
        assert parsed_output['ptr'] == ['ptr.example.com']

    async def test_reverse_resolve_ip_output_processing(self, reverse_resolve_ip_plugin, mock_process_factory, sample_reverse_resolve_ip_output):
        # Test the full nuclei output processing
        test_data = [
            (json.dumps(sample_reverse_resolve_ip_output) + '\n').encode()
        ]
        
        mock_process = mock_process_factory(test_data)
        
        params = {"target": "1.1.1.1"}
        async for result in reverse_resolve_ip_plugin.execute(params):
            assert result['ptr'] == ['ptr.example.com']