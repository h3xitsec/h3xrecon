from typing import AsyncGenerator, Dict, Any
from h3xrecon.workers.plugins.base import ReconPlugin
from loguru import logger
import asyncio
import json
import os
import dns.resolver
import random
import string

class TestDomainCatchall(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    def random_string(self, length=10):
        """Generate a random string of fixed length."""
        letters = string.ascii_lowercase
        return ''.join(random.choice(letters) for i in range(length))
    
    def check_catchall(self, domain, resolver=None):
        """Check if a domain is a DNS catchall."""
        random_subdomain = f"{self.random_string()}.{domain}"
        try:
            resolver.resolve(random_subdomain, 'A')
            return True
        except dns.resolver.NXDOMAIN:
            return False
        except dns.resolver.NoAnswer:
            return False
        except dns.resolver.Timeout:
            return False
        except Exception as e:
            return False

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {target}")
        
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8']  # Using Google's DNS server, you can change this if needed
        
        is_catchall = self.check_catchall(target, resolver)
        
        result = {
            "domain": target,
            "is_catchall": is_catchall
        }
        
        yield result