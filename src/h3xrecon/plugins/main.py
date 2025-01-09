from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.core.utils import is_valid_url, is_valid_hostname, get_domain_from_url, is_valid_ip, is_valid_cidr, parse_url
from loguru import logger
import asyncio

class ReconPlugin(ABC):
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 120

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the recon function."""
        pass

    @abstractmethod
    async def execute(self, params: dict) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute the recon function on the target."""
        pass
    
    async def is_valid_input(self, params: dict) -> bool:
        """Check if the input is valid for the plugin."""
        return True

    async def format_input(self, params: dict) -> dict:
        """Format the input for the plugin."""
        return params
    
    def get_target_type(self, target: str) -> str:
        """Get the type of target."""
        if is_valid_url(target):
            return "url"
        elif is_valid_ip(target):
            return "ip"
        elif is_valid_hostname(target):
            return "domain"
        elif is_valid_cidr(target):
            return "cidr"
        else:
            raise ValueError(f"Invalid target: {target}")

    async def format_targets(self, target: str) -> List[str]:
        """Format the targets for the plugin."""
        from h3xrecon.core.database import DatabaseManager
        db = DatabaseManager()
        _fixed_targets = []
        _target_type = self.get_target_type(target)
        logger.debug(f"TARGET TYPE: {_target_type}")

        #If the target type is not in the target_types list, we need to fix it
        if _target_type not in self.target_types:
            logger.debug(f"TARGET TYPE NOT IN TARGET TYPES: {_target_type} not in {self.target_types}")
            # URL target but need domain
            if _target_type == "url" and 'url' not in self.target_types:
                logger.debug(f"URL TARGET BUT NEED DOMAIN: {target}")
                _fixed_targets.append(get_domain_from_url(target))
                return _fixed_targets
            # Domain target but need url, will fetch all websites with the same domain
            elif _target_type == "domain" and 'url' in self.target_types and 'domain' not in self.target_types:
                logger.debug(f"DOMAIN TARGET BUT NEED URL: {target}")
                # Fetch all websites with the same domain
                _websites = await db._fetch_records('''
                    SELECT * FROM websites WHERE host = $1
                ''', target)
                if _websites.success and isinstance(_websites.data, list) and len(_websites.data) > 0:
                    _fixed_targets += ([website.get('url') for website in _websites.data])
                    return _fixed_targets
            elif _target_type == 'cidr':
                logger.debug(f"CIDR TARGET: {target}")
                _fixed_targets.append(target)
                return _fixed_targets
        else:
            logger.debug(f"TARGET TYPE IN TARGET TYPES: {_target_type} in {self.target_types}")
            _fixed_targets.append(target)
        return _fixed_targets

    async def _read_subprocess_output(self, process: asyncio.subprocess.Process) -> AsyncGenerator[str, None]:
        """Helper method to read and process subprocess output."""
        while True:
            try:
                line = await process.stdout.readuntil(b'\n')
                output = line.decode().strip()
                if output:
                    yield output
            except asyncio.exceptions.IncompleteReadError:
                break
            except asyncio.exceptions.LimitOverrunError:
                partial = await process.stdout.read(1024*1024)
                if partial:
                    output = partial.decode().strip()
                    if output:
                        yield output
                continue
            except Exception as e:
                logger.error(f"Error reading subprocess output: {str(e)}")
                break

        await process.wait()
