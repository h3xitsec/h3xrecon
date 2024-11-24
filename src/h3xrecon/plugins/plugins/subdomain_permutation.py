from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import *
from loguru import logger
import asyncio
import os

class SubdomainPermutation(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, target: str, program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug("Checking if the target is a dns catchall domain")
        
        logger.info(f"Running {self.name} on {target}")
        command = f"""
            echo "{target}" > /tmp/gotator_input.txt
            gotator -sub /tmp/gotator_input.txt -perm /app/Worker/files/permutations.txt -depth 1 -numbers 10 -mindup -adv -md
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        to_test = []
        async for output in self._read_subprocess_output(process):
            # Prepare the message for reverse_resolve_ip
            to_test.append(output)

        message = {
            "function": "resolve_domain",
            "target": target,
            "to_test": to_test
        }
        yield message

        await process.wait()
    
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        self.config = Config()
        self.qm = QueueManager(self.config.nats)
        self.db = db #DatabaseManager(self.config.database.to_dict())
        is_catchall = await self.db.execute_query("SELECT is_catchall FROM domains WHERE domain = $1", output_msg.get("output").get("target"))
        logger.info(is_catchall)
        if is_catchall[0].get("is_catchall"):
            logger.info(f"Target {output_msg.get('output').get('target')} is a dns catchall domain, skipping subdomain permutation processing.")
        elif is_catchall[0].get("is_catchall") is None:
            logger.info(f"Failed to check if target {output_msg.get('output').get('target')} is a dns catchall domain.")
            await self.qm.publish_message(
                subject="function.execute",
                stream="FUNCTION_EXECUTE",
                message={
                    "function": "test_domain_catchall",
                    "program_id": output_msg.get("program_id"),
                    "params": {"target": output_msg.get("output").get("target")},
                    "force": False
                }
            )
        else:
            for t in output_msg.get("output").get("to_test"):
                await self.qm.publish_message(
                    subject="function.execute",
                    stream="FUNCTION_EXECUTE",
                    message={
                        "function": output_msg.get("output").get("function"),
                        "program_id": output_msg.get("program_id"),
                        "params": {"target": t},
                        "force": False
                    }
                )
