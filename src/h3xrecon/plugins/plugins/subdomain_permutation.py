from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_domain_data
from loguru import logger
import asyncio
import os

class SubdomainPermutation(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug("Checking if the target is a dns catchall domain")
        
        logger.debug(f"Running {self.name} on {params.get("target", {})}")

        # For testing purposes, use a different permutation file for h3xit.io
        if params.get("target", {}) == "h3xit.io":
            permutation_file = "/app/Worker/files/permutation_test.txt"
        else:
            permutation_file = "/app/Worker/files/permutations.txt"
        logger.debug(f"Using permutation file {permutation_file}")
        command = f"echo \"{params.get("target", {})}\" > /tmp/gotator_input.txt && gotator -sub /tmp/gotator_input.txt -perm {permutation_file} -depth 1 -numbers 10 -mindup -adv -md"
        logger.debug(f"Running command {command}")
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
            logger.debug(f"Adding {output} to to_test")
        logger.debug(to_test)
        message = {
            "function_name": "resolve_domain",
            "target": params.get("target", {}),
            "to_test": to_test
        }
        logger.debug(f"Publishing message: {message}")
        yield message

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        is_catchall = await db._fetch_records("SELECT domain, is_catchall FROM domains WHERE domain = $1", output_msg.get("output").get("target"))
        logger.info(is_catchall)
        if len(is_catchall.data) == 0:
            logger.info(f"Domain {output_msg.get('output').get('target')} not found in database. Requesting for insertion.")
            await send_domain_data(qm=qm, data=output_msg.get("output").get("target"), program_id=output_msg.get("program_id"))
            await asyncio.sleep(5)
            await qm.publish_message(
                subject="recon.input",
                stream="RECON_INPUT",
                message={
                    "function_name": "subdomain_permutation",
                    "program_id": output_msg.get("program_id"),
                    "params": {"target": output_msg.get("output").get("target")},
                    "force": True
                }
            )
        else:
            if is_catchall.data[0].get("is_catchall"):
                logger.info(f"Target {output_msg.get('output').get('target')} is a dns catchall domain, skipping subdomain permutation processing.")
                return
            elif is_catchall.data[0].get("is_catchall") is None:
                logger.info(f"Failed to check if target {output_msg.get('output').get('target')} is a dns catchall domain. Requesting a new check.")
                logger.debug("Publishing test_domain_catchall message")
                await qm.publish_message(
                    subject="recon.input",
                    stream="RECON_INPUT",
                    message=[{
                        "function_name": "test_domain_catchall",
                        "program_id": output_msg.get("program_id"),
                        "params": {"target": output_msg.get("output").get("target")},
                        "force": True
                    },{
                        "function_name": "subdomain_permutation",
                        "program_id": output_msg.get("program_id"),
                        "params": {"target": output_msg.get("output").get("target")},
                        "force": True
                    }]
                )

            else:
                for t in output_msg.get("output").get("to_test"):
                    await qm.publish_message(
                        subject="recon.input",
                        stream="RECON_INPUT",
                        message={
                            "function_name": "resolve_domain",
                            "program_id": output_msg.get("program_id"),
                            "params": {"target": t},
                            "force": False
                        }
                    )
