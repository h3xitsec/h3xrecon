import pytest
import asyncio
import sys
from h3xrecon.core import Config
from typing import Dict, Any
from unittest.mock import MagicMock, patch, AsyncMock

@pytest.fixture
def config():
    """Provides a test configuration instance"""
    return Config()

@pytest.fixture
def mock_process_factory():
    """Factory fixture for creating mock processes with custom output"""
    class MockProcess:
        def __init__(self, test_data: list[bytes]):
            self.test_data = test_data
            
        class MockStdout:
            def __init__(self, data_lines: list[bytes]):
                self.data_lines = data_lines
                self.current_index = 0
                
            async def readuntil(self, delimiter: bytes) -> bytes:
                if self.current_index >= len(self.data_lines):
                    raise asyncio.exceptions.IncompleteReadError(b'', 0)
                line = self.data_lines[self.current_index]
                self.current_index += 1
                return line
                
            async def read(self, size: int) -> bytes:
                return b'overflow data\n'
                
        async def wait(self):
            return 0
            
    def create_mock_process(test_data: list[bytes]) -> MockProcess:
        process = MockProcess(test_data)
        process.stdout = MockProcess.MockStdout(test_data)
        return process
        
    return create_mock_process

@pytest.fixture(autouse=True)
async def cleanup_tasks():
    """Cleanup any pending tasks after each test"""
    yield
    # Get all tasks
    tasks = [t for t in asyncio.all_tasks() 
             if t is not asyncio.current_task() 
             and not t.done()]
    
    if tasks:
        # Cancel all pending tasks
        for task in tasks:
            task.cancel()
            
        # Wait for all tasks to be cancelled
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Ensure all tasks are properly cleaned up
        for task in tasks:
            try:
                if not task.done():
                    await task
            except (asyncio.CancelledError, Exception):
                pass

@pytest.fixture(scope="session", autouse=True)
def event_loop_policy():
    """Set event loop policy for the test session"""
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    else:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

@pytest.fixture
def sample_reverse_resolve_ip_output() -> Dict[str, Any]:
    """Sample Reverse Resolve IP output for testing"""
    return {
        "ptr": ["ptr.example.com"]
    }

@pytest.fixture
def mock_nats_connect():
    with patch('nats.connect', new_callable=AsyncMock) as mock_connect:
        mock_nats_client = MagicMock()
        mock_connect.return_value = mock_nats_client
        yield mock_connect, mock_nats_client

@pytest.fixture
def mock_queue():
    return MagicMock()

## Resolve Domain Fixtures
@pytest.fixture
def sample_resolve_domain_execute_output_without_cnames():
    return {'host': 'www.example.com', 'a_records': ['3.161.213.94'], 'cnames': []}

@pytest.fixture
def sample_resolve_domain_output_without_cnames():
    return {
        "program_id": 206,
        "execution_id": "1ef9681f-8670-40cd-a6de-df01c9be34fb",
        "source": {
            "function": "resolve_domain",
            "params": {
                "target": "www.example.com",
                "extra_params": []
            },
            "force": False
        },
        "output": {
            "host": "www.example.com",
            "a_records": [
                "3.161.213.94"
            ],
            "cnames": []
        },
        "timestamp": "2024-12-04T14:40:45.978092+00:00"
    }

@pytest.fixture
def sample_resolve_domain_execute_output_with_cnames():
    return {'host': 'www.example.com', 'a_records': ['3.161.213.94'], 'cnames': ['cname.example.com']}

@pytest.fixture
def sample_resolve_domain_output_with_cnames():
    return {
        "program_id": 206,
        "execution_id": "1ef9681f-8670-40cd-a6de-df01c9be34fb",
        "source": {
            "function": "resolve_domain",
            "params": {
                "target": "www.example.com",
                "extra_params": []
            },
            "force": False
        },
        "output": {
            "host": "www.example.com",
            "a_records": [
                "3.161.213.94"
            ],
            "cnames": [
                "cname.example.com"
            ]
        },
        "timestamp": "2024-12-04T14:40:45.978092+00:00"
    }

@pytest.fixture
def sample_reverse_resolve_ip_execute_output_with_single_ptr():
    return "ptr.example.com"

@pytest.fixture
def sample_reverse_resolve_ip_execute_output_with_multiple_ptrs():
    return [
        "ptr.example.com",
        "ptr2.example.com"
    ]

@pytest.fixture
def sample_reverse_resolve_ip_output():
    return {
        "program_id": 206,
        "execution_id": "c38ba702-069f-4f1b-bb7a-519460143952",
        "source": {
            "function": "reverse_resolve_ip",
            "params": {
                "target": "1.1.1.1",
                "extra_params": []
            },
            "force": False
        },
        "output": {
            "domain": "one.one.one.one"
        },
        "timestamp": "2024-12-04T15:15:03.268588+00:00"
    }

## Nuclei Fixtures
@pytest.fixture
def sample_nuclei_execute_output():
    return {
        "output": {
            "url": "https://sub.example.com",
            "matched_at": "https://sub.example.com",
            "type": "http",
            "ip": "1.2.3.4",
            "port": 443,
            "scheme": "https",
            "template_path": "/home/h3x/nuclei-templates/http/technologies/interactsh-server.yaml",
            "template_id": "interactsh-server",
            "template_name": "Interactsh Server",
            "severity": "info"
        },
        "program_id": "1",
        "in_scope": True
    }

@pytest.fixture
def sample_nuclei_execute_output_missing_fields():
    return {
        "output": {
            "url": "https://sub.example.com",
            "type": "http",
            "ip": "1.2.3.4",
            "port": 443,
            "scheme": "https",
            "template_path": "/home/h3x/nuclei-templates/http/technologies/interactsh-server.yaml",
            "template_id": "interactsh-server",
            "template_name": "Interactsh Server",
            "severity": "info",
        },
        "in_scope": True,
        "program_id": "1"
    }

@pytest.fixture
def sample_nuclei_execute_output_tcp():
    return {
        "output": {
            "url": "1.2.3.4:22",
            "matched_at": "1.2.3.4:22",
            "type": "tcp",
            "ip": "1.2.3.4",
            "port": 22,
            "scheme": "",
            "template_path": "tcp/services/sample-service.yaml",
            "template_id": "sample-service",
            "template_name": "Sample Service",
            "severity": "info",
        },
        "in_scope": True,
        "program_id": "1"
    }

@pytest.fixture
def sample_nuclei_execute_output_out_of_scope():
    return {
        "output": {
            "url": "https://sub.example.com",
            "matched_at": "https://sub.example.com",
            "type": "http",
            "ip": "1.2.3.4",
            "port": 443,
            "scheme": "https",
            "template_path": "/home/h3x/nuclei-templates/http/technologies/interactsh-server.yaml",
            "template_id": "interactsh-server",
            "template_name": "Interactsh Server",
            "severity": "info"
        },
        "in_scope": False,
        "program_id": "test_program_123"
    }

@pytest.fixture
def sample_nuclei_execute_output_http():
    return {
        "curl-command": "curl -X 'GET' -H 'Accept: */*' -H 'Accept-Language: en' -H 'User-Agent: Mozilla/5.0 (CentOS; Linux i686; rv:127.0) Gecko/20100101 Firefox/127.0' 'https://i.example.com'",
        "host": "i.h3x.it",
        "info": {
            "author": [
                "convisoappsec",
                "dawid-czarnecki",
                "forgedhallpass",
                "g4l1t0",
                "geeknik",
                "jub0bs",
                "kurohost",
                "socketz",
                "userdehghani"
            ],
            "description": "This template searches for missing HTTP security headers. The impact of these missing headers can vary.\n",
            "metadata": {
                "max-request": 1
            },
            "name": "HTTP Missing Security Headers",
            "severity": "info",
            "tags": [
                "generic",
                "headers",
                "misconfig"
            ]
        },
        "ip": "20.151.252.42",
        "matched-at": "https://i.example.com",
        "matcher-name": "referrer-policy",
        "matcher-status": True,
        "port": 443,
        "scheme": "https",
        "template": "http/misconfiguration/http-missing-security-headers.yaml",
        "template-id": "http-missing-security-headers",
        "template-path": "/home/h3x/nuclei-templates/http/misconfiguration/http-missing-security-headers.yaml",
        "template-url": "https://cloud.projectdiscovery.io/public/http-missing-security-headers",
        "timestamp": "2024-12-04T08:09:07.468459385-05:00",
        "type": "http",
        "url": "https://i.example.com"
    }

@pytest.fixture
def sample_nuclei_output_tcp():
    return {
        "extracted-results": [
            "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1"
        ],
        "host": "192.168.0.14:22",
        "info": {
            "author": [
                "daffainfo",
                "iamthefrogy",
                "r3dg33k"
            ],
            "classification": {
                "cve-id": None,
                "cvss-metrics": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N",
                "cwe-id": [
                    "cwe-200"
                ]
            },
            "description": "OpenSSH service was detected.\n",
            "metadata": {
                "max-request": 1
            },
            "name": "OpenSSH Service - Detect",
            "reference": [
                "http://seclists.org/fulldisclosure/2016/Jul/51",
                "http://www.openwall.com/lists/oss-security/2016/08/01/2",
                "http://www.openwall.com/lists/oss-security/2018/08/15/5",
                "https://nvd.nist.gov/vuln/detail/CVE-2016-6210",
                "https://nvd.nist.gov/vuln/detail/CVE-2018-15473"
            ],
            "severity": "info",
            "tags": [
                "detect",
                "detection",
                "network",
                "openssh",
                "seclists",
                "ssh",
                "tcp"
            ]
        },
        "ip": "192.168.0.14",
        "matched-at": "192.168.0.14:22",
        "matcher-status": True,
        "port": 22,
        "template": "network/detection/openssh-detect.yaml",
        "template-id": "openssh-detect",
        "template-path": "/home/h3x/nuclei-templates/network/detection/openssh-detect.yaml",
        "template-url": "https://cloud.projectdiscovery.io/public/openssh-detect",
        "timestamp": "2024-12-04T08:11:27.222345651-05:00",
        "type": "tcp",
        "url": "192.168.0.14:22"
    }