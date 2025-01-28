from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from loguru import logger
import os

class Sleep(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug(f"Running {self.name} for {params.get('target', {})} seconds")
        command = f"sleep {params.get('target', 45)} && echo 'sleep completed'"
        logger.debug(f"Running command: {command}")
        process = await self._create_subprocess_shell(command)
        
        async for output in self._read_subprocess_output(process):
            yield "sleep completed"

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:    
        logger.debug(f"Processing output: {output_msg}")
        #self.log_or_update_function_execution(output_msg)