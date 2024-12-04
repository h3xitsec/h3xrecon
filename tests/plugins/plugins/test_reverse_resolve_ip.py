import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from h3xrecon.plugins.plugins.reverse_resolve_ip import ReverseResolveIP
import asyncio
import json
@pytest.fixture
def mock_nats_connect():
    with patch('nats.connect', new_callable=AsyncMock) as mock_connect:
        # Create a mock NATS client
        mock_nats_client = MagicMock()
        mock_connect.return_value = mock_nats_client
        yield mock_connect, mock_nats_client
    # Teardown can be handled here if necessary

@pytest.mark.asyncio
class TestReverseResolveIPPlugin:
    
    @pytest.fixture
    def reverse_resolve_ip_plugin(self):
        return ReverseResolveIP()
    
    async def _mock_read_subprocess_output(self, process, test_data):
        """Helper method to mock subprocess output"""
        for line in test_data:
            yield line.decode()
    
    # Test that reverse_resolve_ip execute method correctly parses output
    async def test_reverse_resolve_ip_execute_with_single_ptr(self, reverse_resolve_ip_plugin, mock_process_factory, sample_reverse_resolve_ip_execute_output_with_single_ptr):
        """
        Test the execute method with valid JSON output.
        """
        # Prepare test data as invalid JSON bytes
        test_data = [
            (json.dumps(sample_reverse_resolve_ip_execute_output_with_single_ptr) + '\n').encode()
        ]
        
        # Create mock process using the factory
        mock_process = mock_process_factory(test_data)
        
        # Patch the _read_subprocess_output method to use our mock process
        reverse_resolve_ip_plugin._read_subprocess_output = lambda p: self._mock_read_subprocess_output(p, test_data)
        
        # Prepare parameters for execution
        params = {
            "target": "1.1.1.1"
        }
        
        # Collect results from execute method
        results = []
        async for result in reverse_resolve_ip_plugin.execute(params):
            results.append(result)
        
        # Assert we got exactly one result
        assert len(results) == 1
        
        # Verify the result matches expected output
        result = results[0]
        assert result == {"domain": "ptr.example.com"}



    # Test that process_output correctly calls helper functions with valid output_msg.
    @patch('h3xrecon.plugins.plugins.reverse_resolve_ip.send_domain_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.reverse_resolve_ip.send_ip_data', new_callable=AsyncMock)
    async def test_process_output(
        self,
        mock_send_ip_data,
        mock_send_domain_data,
        reverse_resolve_ip_plugin,
        sample_reverse_resolve_ip_output
    ):
        """
        Test that process_output correctly calls helper functions with valid output_msg.
        """
        await reverse_resolve_ip_plugin.process_output(sample_reverse_resolve_ip_output)
    
        # Assert helper functions are called once each with correct parameters
        mock_send_domain_data.assert_awaited_once_with(
            data=[sample_reverse_resolve_ip_output['output']['domain']],
            program_id=sample_reverse_resolve_ip_output['program_id']
        )
        mock_send_ip_data.assert_awaited_once_with(
            data=sample_reverse_resolve_ip_output['source']['params']['target'], 
            program_id=sample_reverse_resolve_ip_output['program_id']
        )