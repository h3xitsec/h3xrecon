from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any
import asyncio
from loguru import logger

class ReconPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the recon function."""
        pass

    @abstractmethod
    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute the recon function on the target."""
        pass

    async def _read_subprocess_output(self, process: asyncio.subprocess.Process) -> AsyncGenerator[str, None]:
        """Helper method to read and process subprocess output."""
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            output = line.decode().strip()
            if output:
                #logger.debug(f"{self.name} output: {output}")
                yield output

        await process.wait()
