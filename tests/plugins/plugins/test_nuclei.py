import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from h3xrecon.plugins.plugins.nuclei import Nuclei, FunctionOutput
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
class TestNucleiPlugin:

    @pytest.fixture
    def nuclei_plugin(self):
        return Nuclei()
    
    async def _mock_read_subprocess_output(self, process, test_data):
        """Helper method to mock subprocess output"""
        for line in test_data:
            yield line.decode()
    
    # Test that nuclei execute method correctly parses HTTP output
    async def test_nuclei_execute_with_http_output(self, nuclei_plugin, mock_process_factory, sample_nuclei_execute_output_http):
        """Test the execute method with HTTP output."""
        # Prepare test data
        test_data = [(json.dumps(sample_nuclei_execute_output_http) + '\n').encode()]
        
        # Create mock process
        mock_process = mock_process_factory(test_data)
        
        # Replace the read method with a simple sync-to-async converter
        async def quick_read(process):
            for line in test_data:
                yield line.decode()
                
        nuclei_plugin._read_subprocess_output = quick_read
        
        # Execute and collect results
        results = []
        async for result in nuclei_plugin.execute({
            "target": "example.com", 
            "extra_params": ["-t", "http/misconfiguration"]
        }):
            results.append(result)
        
        # Assert we got exactly one result
        assert len(results) == 1
        
        # Verify the result matches expected output
        result = results[0]
        assert str(result['url']) == f"{sample_nuclei_execute_output_http['url']}"
        assert str(result['matched_at']) == f"{sample_nuclei_execute_output_http['matched-at']}"
        assert result['type'] == sample_nuclei_execute_output_http['type']
        assert str(result['ip']) == sample_nuclei_execute_output_http['ip']
        assert result['port'] == sample_nuclei_execute_output_http['port']
        assert result['template_path'] == sample_nuclei_execute_output_http['template']
        assert result['template_id'] == sample_nuclei_execute_output_http['template-id']
        assert result['template_name'] == sample_nuclei_execute_output_http['info']['name']
        assert result['severity'] == sample_nuclei_execute_output_http['info']['severity']
        assert result['scheme'] == sample_nuclei_execute_output_http['scheme']

    # Test that nuclei execute method correctly parses TCP output
    async def test_nuclei_execute_with_tcp_output(self, nuclei_plugin, mock_process_factory, sample_nuclei_output_tcp):
        """
        Test the execute method with invalid JSON output.
        """
        # Prepare test data as invalid JSON bytes
        test_data = [
            (json.dumps(sample_nuclei_output_tcp) + '\n').encode()
        ]
        
        # Create mock process using the factory
        mock_process = mock_process_factory(test_data)
        
        # Patch the _read_subprocess_output method to use our mock process
        nuclei_plugin._read_subprocess_output = lambda p: self._mock_read_subprocess_output(p, test_data)
        
        # Prepare parameters for execution
        params = {
            "target": "example.com", 
            "extra_params": ["-t", "network/detection"]
        }
        
        # Collect results from execute method
        results = []
        async for result in nuclei_plugin.execute(params):
            results.append(result)
        
        # Assert we got exactly one result
        assert len(results) == 1
        
        # Verify the result matches expected output
        result = results[0]
        assert str(result['url']) == f"{sample_nuclei_output_tcp['url']}"
        assert str(result['matched_at']) == f"{sample_nuclei_output_tcp['matched-at']}"
        assert result['type'] == sample_nuclei_output_tcp['type']
        assert str(result['ip']) == sample_nuclei_output_tcp['ip']
        assert result['port'] == sample_nuclei_output_tcp['port']
        assert result['template_path'] == sample_nuclei_output_tcp['template']
        assert result['template_id'] == sample_nuclei_output_tcp['template-id']
        assert result['template_name'] == sample_nuclei_output_tcp['info']['name']
        assert result['severity'] == sample_nuclei_output_tcp['info']['severity']
        assert result['scheme'] == ""
    

    # Test that process_output correctly calls helper functions with valid output_msg.
    @patch('h3xrecon.plugins.plugins.nuclei.send_service_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_nuclei_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_ip_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_domain_data', new_callable=AsyncMock)
    async def test_process_output_with_mocked_helpers(
        self,
        mock_send_domain_data,
        mock_send_ip_data,
        mock_send_nuclei_data,
        mock_send_service_data,
        nuclei_plugin,
        sample_nuclei_execute_output
    ):
        """
        Test that process_output correctly calls helper functions with valid output_msg.
        """
        await nuclei_plugin.process_output(sample_nuclei_execute_output)
    
        # Assert helper functions are called once each with correct parameters
        mock_send_domain_data.assert_awaited_once_with(
            data="sub.example.com",
            program_id=sample_nuclei_execute_output['program_id'],
            qm=None
        )
        mock_send_ip_data.assert_awaited_once_with(
            data="1.2.3.4", 
            program_id=sample_nuclei_execute_output['program_id'],
            qm=None
        )
        mock_send_nuclei_data.assert_awaited_once_with(
            data=sample_nuclei_execute_output['output'], 
            program_id=sample_nuclei_execute_output['program_id'],
            qm=None
        )
        mock_send_service_data.assert_awaited_once_with(
            data={
                "ip": "1.2.3.4",
                "port": 443,
                "protocol": "tcp",
                "state": "open",
                "service": "https",
            }, 
            program_id=sample_nuclei_execute_output['program_id'],
            qm=None
        )

    @patch('h3xrecon.plugins.plugins.nuclei.send_service_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_nuclei_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_ip_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_domain_data', new_callable=AsyncMock)
    async def test_process_output_tcp_with_mocked_helpers(
        self,
        mock_send_domain_data,
        mock_send_ip_data,
        mock_send_nuclei_data,
        mock_send_service_data,
        nuclei_plugin,
        sample_nuclei_execute_output_tcp
    ):
        """
        Test that process_output correctly calls helper functions with non-HTTP output_msg.
        """
        await nuclei_plugin.process_output(sample_nuclei_execute_output_tcp)
    
        # Assert helper functions are called once each with correct parameters
        # mock_send_domain_data.assert_awaited_once_with(
        #     data="1.2.3.4",
        #     program_id=sample_nuclei_execute_output_non_http['program_id']
        # )
        # Assert that an IP is sent with the correct parameters
        mock_send_ip_data.assert_awaited_once_with(
            data="1.2.3.4",
            program_id=sample_nuclei_execute_output_tcp['program_id']
        )
        # Assert that nuclei data is sent with the correct parameters
        mock_send_nuclei_data.assert_awaited_once_with(
            data=sample_nuclei_execute_output_tcp['output'],
            program_id=sample_nuclei_execute_output_tcp['program_id']
        )
        # Assert that a service is sent with the correct parameters
        mock_send_service_data.assert_awaited_once_with(
            data={
                "ip": "1.2.3.4",
                "port": 22,
                "protocol": "tcp",
                "state": "open",
                "service": "",
            }, 
            program_id=sample_nuclei_execute_output_tcp['program_id']
        )

    # Test that process_output does not call helper functions when in_scope is False.
    @patch('h3xrecon.plugins.plugins.nuclei.send_service_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_nuclei_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_ip_data', new_callable=AsyncMock)
    @patch('h3xrecon.plugins.plugins.nuclei.send_domain_data', new_callable=AsyncMock)
    async def test_process_output_out_of_scope(
        self,
        mock_send_domain_data,
        mock_send_ip_data,
        mock_send_nuclei_data,
        mock_send_service_data,
        nuclei_plugin,
        sample_nuclei_execute_output_out_of_scope
    ):
        """
        Test that process_output does not call helper functions when in_scope is False.
        """
        await nuclei_plugin.process_output(sample_nuclei_execute_output_out_of_scope)

        # Assert helper functions are not called
        mock_send_domain_data.assert_not_awaited()
        mock_send_ip_data.assert_not_awaited()
        mock_send_nuclei_data.assert_not_awaited()
        mock_send_service_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nuclei_output_serialization(self, nuclei_plugin):
        """Test that the nuclei output can be properly serialized to JSON"""
        # Create a FunctionOutput object with an IP (this simulates what happens in execute())
        nuclei_output = FunctionOutput(
            url="https://example.com",
            matched_at="https://example.com",
            type="http",
            ip="1.2.3.4",  # This gets converted to IPv4Address by Pydantic
            port=443,
            scheme="https",
            template_path="/path/to/template",
            template_id="template-id",
            template_name="Template Name",
            severity="info"
        )
        
        # Simulate the worker's message structure
        worker_message = {
            'program_id': 1,
            'execution_id': 'test-execution',
            'source': {
                'function': 'nuclei',
                'params': {'target': 'example.com'}
            },
            'output': nuclei_output.model_dump(),  # This is what actually happens in execute()
            'in_scope': True
        }
        
        # Try to serialize the entire message
        try:
            json_str = json.dumps(worker_message)
        except TypeError as e:
            pytest.fail(f"Failed to serialize worker message: {e}")
        
        # Verify we can deserialize it back
        parsed = json.loads(json_str)
        assert isinstance(parsed['output']['ip'], str)