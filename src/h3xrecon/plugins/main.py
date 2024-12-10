from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any
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
