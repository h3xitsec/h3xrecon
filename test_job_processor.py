import json
import unittest
from nats.aio.client import Client as NATS
import asyncio
import psycopg2
import uuid
from psycopg2.extras import RealDictCursor
from datetime import datetime

def get_db_connection():
    return psycopg2.connect(
        host="processor",
        database="h3xrecon",
        user="h3xrecon",
        password="h3xrecon"
    )

class TestJobProcessorMessages(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.nc = NATS()
        await self.nc.connect("nats://processor:4222")
        self.received_messages = []
        await self.nc.subscribe("recon.test.data", cb=self.message_handler)

    async def asyncTearDown(self):
        await self.nc.close()

    async def message_handler(self, msg):
        data = json.loads(msg.data.decode())
        self.received_messages.append(data)

    async def send_and_validate(self, message, expected_results):
        message["execution_id"] = str(uuid.uuid4())
        message["timestamp"] = datetime.now().isoformat()
        message["nolog"] = True
        message["recon_data_queue"] = "recon.test.data"
        await self.nc.publish("function.output", json.dumps(message).encode())
        
        await asyncio.sleep(3)
        
        for expected_result in expected_results:
            self.assertIn(expected_result, self.received_messages, 
                        f"Expected message {expected_result} not found in received messages {self.received_messages[0]}.")
        
        print(f"Validation successful for message: {message}")
        print(f"Received messages: {self.received_messages}")

    async def test_job_processor_sends_correct_messages(self):
        test_cases = [
            {
                "input": {
                    "program_id": 3,
                    "source": {
                        "function": "resolve_domain",
                        "target": "example.net"
                    },
                    "data": {
                        "host": "example.net",
                        "a_records": [
                            "23.58.127.137",
                            "23.58.127.153"
                        ],
                        "cnames": [
                            "example.net.edgekey.net",
                            "e107536.a.akamaiedge.net"
                        ]
                    }
                },
                "expected": [
                    {
                        "program_id": 3,
                        "data_type": "ip",
                        "data": ["23.58.127.137"]
                    },
                    {
                        "program_id": 3,
                        "data_type": "domain",
                        "data": ["example.net"],
                        "attributes": {
                            "cnames": [
                                "example.net.edgekey.net",
                                "e107536.a.akamaiedge.net"
                            ],
                            "ips": [
                                "23.58.127.137",
                                "23.58.127.153"
                            ]
                        }
                    }
                ]
            },
            {
                "input": {
                    "program_id": 3,
                    "source": {"function": "test_http", "target": "example.net"},
                    "data": {
                        "timestamp": "2024-10-22T19:44:43.563610154Z",
                        "port": "443",
                        "url": "https://example.net:443",
                        "input": "example.net",
                        "title": "Services financiers aux particuliers - Desjardins",
                        "scheme": "https",
                        "resolvers": ['1.0.0.1:53', '8.8.8.8:53']
                    }
                },
                "expected": [
                    {
                        'program_id': 3,
                        'data_type': 'url',
                        'data': {
                            'url': 'https://example.net:443',
                            'attributes': {
                                'status_code': None,
                                'chain_status_codes': None,
                                'title': 'Services financiers aux particuliers - Desjardins',
                                'final_url': None,
                                'scheme': 'https',
                                'port': '443',
                                'webserver': None,
                                'content_type': None,
                                'content_length': None,
                                'tech': None
                            }
                        }
                    }
                ]
            },
            {
                "input": {
                    "program_id": 3,
                    "source": {"function": "test_http", "target": "example.net"},
                    "data": {
                        "timestamp": "2024-10-22T19:44:43.563610154Z",
                        "port": "443",
                        "url": "https://example.net:443",
                        "input": "example.net",
                        "status_code": 200,
                        "chain_status_codes": [302, 200],
                        "title": "Services financiers aux particuliers - Desjardins",
                        "scheme": "https",
                        "resolvers": ['1.0.0.1:53', '8.8.8.8:53']
                    }
                },
                "expected": [
                    {
                        'program_id': 3,
                        'data_type': 'url',
                        'data': {
                            'url': 'https://example.net:443',
                            'attributes': {
                                'status_code': 200,
                                'chain_status_codes': [302, 200],
                                'title': 'Services financiers aux particuliers - Desjardins',
                                'final_url': None,
                                'scheme': 'https',
                                'port': '443',
                                'webserver': None,
                                'content_type': None,
                                'content_length': None,
                                'tech': None
                            }
                        }
                    }
                ]
            },
            {
                "input": {
                    "program_id": 3,
                    "source": {"function": "test_http", "target": "example.net"},
                    "data": {
                        "timestamp": "2024-10-22T19:44:43.563610154Z",
                        "port": "443",
                        "url": "https://example.net:443",
                        "input": "example.net",
                        "status_code": 200,
                        "tech": ["Adobe Experience Manager", "HSTS", "Java"],
                        "chain_status_codes": [302, 200],
                        "title": "Services financiers aux particuliers - Desjardins",
                        "scheme": "https",
                        "resolvers": ['1.0.0.1:53', '8.8.8.8:53']
                    }
                },
                "expected": [
                    {
                        'program_id': 3,
                        'data_type': 'url',
                        'data': {
                            'url': 'https://example.net:443',
                            'attributes': {
                                'status_code': 200,
                                'chain_status_codes': [302, 200],
                                'title': 'Services financiers aux particuliers - Desjardins',
                                'final_url': None,
                                'scheme': 'https',
                                'port': '443',
                                'webserver': None,
                                'content_type': None,
                                'content_length': None,
                                'tech': ['Adobe Experience Manager', 'HSTS', 'Java']
                            }
                        }
                    }
                ]
            },
            {
                "input": {'program_id': 3, 'source': {'function': 'find_subdomains_ctfr', 'target': 'example.com'}, 'data': {'subdomain': ['subdomain.example.com']}},
                "expected": [
                    {
                        'program_id': 3,
                        'data_type': 'domain',
                        'data': ['subdomain.example.com']
                    }
                ]
            }
        ]

        for case in test_cases:
            with self.subTest(case=case):
                await self.send_and_validate(case["input"], case["expected"])

if __name__ == "__main__":
    unittest.main()
