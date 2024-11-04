import json
import time
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
import unittest
from QueueManager import QueueManager

def get_db_connection():
    return psycopg2.connect(
        host="processor",
        database="h3xrecon",
        user="h3xrecon",
        password="h3xrecon"
    )

class TestDataInsertion(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.qm = QueueManager()

    async def asyncTearDown(self):
        await self.qm.close()

    async def send_and_validate(self, message, validation_query, expected_result):
        await self.qm.publish_message(subject='recon.data', stream='RECON_DATA', message=json.dumps(message))
        
        await asyncio.sleep(1)
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(validation_query)
                result = cur.fetchone()
        
        self.assertIsNotNone(result, f"No result found for message: {message}")
        print(result)
        print(expected_result)
        for key, value in expected_result.items():
            self.assertEqual(result[key], value, f"Mismatch in {key} for message: {message}")
        
        print(f"Validation successful for message: {message}")
        print(f"Database result: {result}")

    async def test_ip_insertion(self):
        test_cases = [
            {
                "message": {"program_id": 3, "data_type": "ip", "data": ["192.168.1.1"], "attributes": {}},
                "query": "SELECT * FROM ips WHERE ip = '192.168.1.1'",
                "expected": {"ip": "192.168.1.1", "program_id": 3}
            },
            {
                "message": {"program_id": 3, "data_type": "service", "data": [{"ip": "192.168.1.1", "port": 443, "protocol": "tcp"}]},
                "query": "SELECT * FROM services WHERE ip = (SELECT id from ips where ip = '192.168.1.1') AND port = 443 AND protocol = 'tcp'",
                "expected": {"ip": 1, "port": 443, "protocol": "tcp", "program_id": 3}
            }
            # {
            #     "message": {"program_id": 3, "data_type": "ip", "data": ["192.168.1.1"], "attributes": {"ptr": "ptr.desjardins.com"}},
            #     "query": "SELECT * FROM ips WHERE ip = '192.168.1.1'",
            #     "expected": {"ip": "192.168.1.1", "ptr": "ptr.desjardins.com", "program_id": 3}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "ip", "data": ["192.168.1.2"]},
            #     "query": "SELECT * FROM ips WHERE ip = '192.168.1.2'",
            #     "expected": {"ip": "192.168.1.2", "program_id": 3}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "domain", "data": ["test1.desjardins.com"], "attributes": {"ips": ["192.168.1.1"], "cnames": ["alias1.desjardins.com"]}},
            #     "query": "SELECT * FROM domains where domain = 'test1.desjardins.com'",
            #     "expected": {"domain":"test1.desjardins.com","ips":[1], "cnames":["alias1.desjardins.com"]}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "domain", "data": ["test2.desjardins.com"], "attributes": {"ips": ["192.168.1.1", "192.168.1.2"]}},
            #     "query": "SELECT * FROM domains where domain = 'test2.desjardins.com'",
            #     "expected": {"domain":"test2.desjardins.com","ips":[1,2]}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "domain", "data": ["test3.desjardins.com"], "attributes": {"is_catchall": True}},
            #     "query": "SELECT * FROM domains where domain = 'test3.desjardins.com'",
            #     "expected": {"domain":"test3.desjardins.com","is_catchall":True}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "url", "data": {"url": "https://test.desjardins.com", "attributes": {"title": "Test Page", "chain_status_codes": [301, 200], "status_code": 200, "final_url": "https://test.desjardins.com/final", "scheme": "https", "port": 443, "webserver": "nginx", "content_type": "text/html", "content_length": 1024, "tech": ["PHP", "MySQL"]}}},
            #     "query": "SELECT * FROM urls where url = 'https://test.desjardins.com'",
            #     "expected": {"url":"https://test.desjardins.com","title":"Test Page","chain_status_codes":[301,200],"status_code":200,"final_url":"https://test.desjardins.com/final","scheme":"https","port":443,"webserver":"nginx","content_type":"text/html","content_length":1024,"tech":["php","mysql"]}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "url", "data": {"url": "http://minimal.desjardins.com"}},
            #     "query": "SELECT * FROM urls where url = 'http://minimal.desjardins.com'",
            #     "expected": {"url":"http://minimal.desjardins.com"}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "domain", "data": ["UPPERCASE.desjardins.com"]},
            #     "query": "SELECT * FROM domains where domain = 'uppercase.desjardins.com'",
            #     "expected": {"domain":"uppercase.desjardins.com"}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "ip", "data": ["192.168.1.3"], "attributes": {"ptr": ["PTR.desjardins.com"]}},
            #     "query": "SELECT * FROM ips where ip = '192.168.1.3'",
            #     "expected": {"ip":"192.168.1.3","ptr":"ptr.desjardins.com","program_id":2}
            # },
            # {
            #     "message": {"program_id": 3, "data_type": "url", "data": {"url": "HTTPS://UPPER.desjardins.com"}},
            #     "query": "SELECT * FROM urls where url = 'https://upper.desjardins.com'",
            #     "expected": {"url":"https://upper.desjardins.com"}
            # }
            # Add more test cases here
        ]

        for case in test_cases:
            with self.subTest(case=case):
                await self.send_and_validate(case["message"], case["query"], case["expected"])

if __name__ == "__main__":
    unittest.main()