from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.plugins.puredns import PureDNSPlugin
from h3xrecon.plugins.helper import send_domain_data
from h3xrecon.core.utils import is_valid_hostname, get_domain_from_url
from loguru import logger
import asyncio
import os
from datetime import datetime
class SubdomainPermutation(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def target_types(self) -> List[str]:
        return ["domain"]

    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_hostname(params.get("target", {}))
    
    async def format_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not is_valid_hostname(params.get("target", {})):
            if params.get("target", {}).startswith("https://") or params.get("target", {}).startswith("http://"):
                params["target"] = get_domain_from_url(params.get("target", {}))
            else:
                params["target"] = params.get("target", {})
        return params
    
    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.debug("Checking if the target is a dns catchall domain")
        
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        
        wordlist = params.get("wordlist", "/app/Worker/files/permutations.txt")
        if not wordlist:
            wordlist = "/app/Worker/files/permutations.txt"
        logger.debug(f"Using permutation file {wordlist}")
        command = f"echo \"{params.get("target", {})}\" > /tmp/gotator_input.txt && gotator -sub /tmp/gotator_input.txt -perm {wordlist} -depth 1 -numbers 10 -mindup -adv -md"
        logger.debug(f"Running command {command}")
        process = await self._create_subprocess_shell(command)
        to_test = []
        async for output in self._read_subprocess_output(process):
            # Prepare the message for reverse_resolve_ip
            to_test.append(output)
        
        message = {
            "target": params.get("target", {}),
            "to_test": to_test
        }
        logger.debug(f"Publishing message: {message}")
        yield message

        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
        # Use puredns plugin to resolve the target and check if it is a wildcard domain
        if output_msg.get("data", {}).get("target"):
            logger.debug(f"Resolving target {output_msg.get('data').get('target')} with puredns")
            puredns = PureDNSPlugin()
            puredns.resolve_target(output_msg.get("data").get("target"))
            parent_domain = ".".join(output_msg.get("data").get('target').split(".")[1:])
            logger.debug(f"Puredns output: {puredns.output}")
            
            # Get the domain's db entry to check if it is a wildcard domain
            is_catchall = output_msg.get("data").get("target") in puredns.output.get("wildcards", []) #await db._fetch_records("SELECT domain, is_catchall FROM domains WHERE domain = $1", output_msg.get("data").get("target"))
            domain = await db._fetch_records("SELECT * FROM domains WHERE domain = $1", output_msg.get("data").get("target"))
            domain = domain.data
            # If the domain is not in the database, request for insertion via the data worker and wait for insertion
            if len(domain) == 0:
                logger.info(f"Domain {output_msg.get("data").get('target')} not found in database. Requesting for insertion.")
                await send_domain_data(
                        qm=qm,
                        data=output_msg.get("data").get("target"),
                        execution_id=output_msg.get('execution_id'),
                        program_id=output_msg.get('program_id'),
                        attributes={
                            "is_catchall": is_catchall
                        },
                        trigger_new_jobs=output_msg.get('trigger_new_jobs', True)
                    )
                # Wait for domain to be inserted (max 30 seconds)
                start_time = datetime.now()
                while True:
                    logger.debug(f"Checking if domain {output_msg.get('data').get('target')} is inserted in database")
                    domain = await db._fetch_records("SELECT * FROM domains WHERE domain = $1", output_msg.get("data").get("target"))
                    domain = domain.data
                    if len(domain) > 0:
                        logger.debug(f"Domain {output_msg.get('data').get('target')} inserted in database")
                        break
                    if (datetime.now() - start_time).total_seconds() > 30:
                        logger.warning(f"Timeout waiting for domain {output_msg.get('data').get('target')} to be inserted")
                        break
                    await asyncio.sleep(2)
                await qm.publish_message(
                    subject="recon.input.subdomain_permutation",
                    stream="RECON_INPUT",
                    message={
                        "function_name": "subdomain_permutation",
                        "program_id": output_msg.get("program_id"),
                        "params": {"target": output_msg.get("source", {}).get("params", {}).get("target"), "wordlist": output_msg.get("source", {}).get("params", {}).get("wordlist", "/app/Worker/files/permutations.txt")},
                        "force": True,
                        "execution_id": output_msg.get('execution_id', None),
                        "trigger_new_jobs": output_msg.get('trigger_new_jobs', True)
                    }
                )
            else:
                if is_catchall:
                    logger.info(f"JOB SKIPPED: Target {output_msg.get("data").get('target')} is a wildcard domain, skipping subdomain permutation processing.")
                    return

                else:
                    if len(output_msg.get("data").get("to_test")) > 0:
                        logger.info(f"TRIGGERING JOB: puredns for {len(output_msg.get("data").get("to_test"))} subdomains to test")
                        for t in output_msg.get("data").get("to_test"):
                            await qm.publish_message(
                                subject="recon.input.puredns",
                                stream="RECON_INPUT",
                                message={
                                    "function_name": "puredns",
                                    "program_id": output_msg.get("program_id"),
                                    "params": {"target": t, "mode": "resolve"},
                                    "force": True,
                                    "execution_id": output_msg.get('execution_id', ""),
                                    "trigger_new_jobs": output_msg.get('trigger_new_jobs', True)
                                }
                            )
        
                        logger.info(f"TRIGGERING JOBS: dnsx for {len(output_msg.get("data").get("to_test"))} subdomains to test")
                        for t in output_msg.get("data").get("to_test"):
                            await qm.publish_message(
                            subject="recon.input.dnsx",
                            stream="RECON_INPUT",
                            message={
                                "function_name": "dnsx",
                                "program_id": output_msg.get("program_id"),
                                "params": {"target": t},
                                "force": True,
                                "execution_id": output_msg.get('execution_id', ""),
                                "trigger_new_jobs": output_msg.get('trigger_new_jobs', True)
                            }
                        )
