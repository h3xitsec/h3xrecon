import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from h3xrecon.plugins.plugins.resolve_domain import ResolveDomain
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
class TestResolveDomainPlugin:
    
    @pytest.fixture
    def resolve_domain_plugin(self):
        return ResolveDomain()
    
    async def _mock_read_subprocess_output(self, process, test_data):
        """Helper method to mock subprocess output"""
        for line in test_data:
            yield line.decode()
    
    # Test that resolve_domain execute method correctly parses output
    async def test_resolve_domain_execute_without_cnames(self, resolve_domain_plugin, mock_process_factory, sample_resolve_domain_execute_output_without_cnames):
        """
        Test the execute method with valid JSON output.
        """
        # Prepare test data as invalid JSON bytes
        test_data = [
            (json.dumps(sample_resolve_domain_execute_output_without_cnames) + '\n').encode()
        ]
        
        # Create mock process using the factory
        mock_process = mock_process_factory(test_data)
        
        # Patch the _read_subprocess_output method to use our mock process
        resolve_domain_plugin._read_subprocess_output = lambda p: self._mock_read_subprocess_output(p, test_data)
        
        # Prepare parameters for execution
        params = {
            "target": "example.com"
        }
        
        # Collect results from execute method
        results = []
        async for result in resolve_domain_plugin.execute(params):
            results.append(result)
        
        # Assert we got exactly one result
        assert len(results) == 1
        
        # Verify the result matches expected output
        result = results[0]
        assert str(result['host']) == f"www.example.com"
        assert str(result['a_records']) == f"['3.161.213.94']"
        assert str(result['cnames']) == f"[]"
    
    # Test that resolve_domain execute method correctly parses output with cnames
    async def test_resolve_domain_execute_with_cnames(self, resolve_domain_plugin, mock_process_factory, sample_resolve_domain_execute_output_with_cnames):
        """
        Test the execute method with valid JSON output.
        """
        # Prepare test data as invalid JSON bytes
        test_data = [
            (json.dumps(sample_resolve_domain_execute_output_with_cnames) + '\n').encode()
        ]
        
        # Create mock process using the factory
        mock_process = mock_process_factory(test_data)
        
        # Patch the _read_subprocess_output method to use our mock process
        resolve_domain_plugin._read_subprocess_output = lambda p: self._mock_read_subprocess_output(p, test_data)
        
        # Prepare parameters for execution
        params = {
            "target": "example.com"
        }
        
        # Collect results from execute method
        results = []
        async for result in resolve_domain_plugin.execute(params):
            results.append(result)
        
        # Assert we got exactly one result
        assert len(results) == 1
        
        # Verify the result matches expected output
        result = results[0]
        assert str(result['host']) == f"www.example.com"
        assert str(result['a_records']) == f"['3.161.213.94']"
        assert str(result['cnames']) == f"['cname.example.com']"

    # Test that process_output correctly calls helper functions with valid output_msg that doesnt have cnames.
    @patch('h3xrecon.plugins.plugins.resolve_domain.send_domain_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.resolve_domain.send_ip_data', new_callable=AsyncMock)
    async def test_process_output_without_cnames(
        self,
        mock_send_ip_data,
        mock_send_domain_data,
        resolve_domain_plugin,
        sample_resolve_domain_output_without_cnames
    ):
        """
        Test that process_output correctly calls helper functions with valid output_msg.
        """
        await resolve_domain_plugin.process_output(sample_resolve_domain_output_without_cnames)
    
        # Assert helper functions are called once each with correct parameters
        mock_send_domain_data.assert_awaited_once_with(
            data=[sample_resolve_domain_output_without_cnames['output']['host']],
            program_id=sample_resolve_domain_output_without_cnames['program_id'],
            attributes={"cnames": sample_resolve_domain_output_without_cnames['output']['cnames'], "ips": sample_resolve_domain_output_without_cnames['output']['a_records']}
        )
        mock_send_ip_data.assert_awaited_once_with(
            data=sample_resolve_domain_output_without_cnames['output']['a_records'][0], 
            program_id=sample_resolve_domain_output_without_cnames['program_id']
        )

    # Test that process_output correctly calls helper functions with valid output_msg that has cnames.
    @patch('h3xrecon.plugins.plugins.resolve_domain.send_domain_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.resolve_domain.send_ip_data', new_callable=AsyncMock)
    async def test_process_output_with_cnames(
        self,
        mock_send_ip_data,
        mock_send_domain_data,
        resolve_domain_plugin,
        sample_resolve_domain_output_with_cnames
    ):
        """
        Test that process_output correctly calls helper functions with valid output_msg.
        """
        await resolve_domain_plugin.process_output(sample_resolve_domain_output_with_cnames)
    
        # Assert helper functions are called once each with correct parameters
        mock_send_domain_data.assert_awaited_once_with(
            data=[sample_resolve_domain_output_with_cnames['output']['host']],
            program_id=sample_resolve_domain_output_with_cnames['program_id'],
            attributes={"cnames": sample_resolve_domain_output_with_cnames['output']['cnames'], "ips": sample_resolve_domain_output_with_cnames['output']['a_records']}
        )
        mock_send_ip_data.assert_awaited_once_with(
            data=sample_resolve_domain_output_with_cnames['output']['a_records'][0], 
            program_id=sample_resolve_domain_output_with_cnames['program_id']
        )