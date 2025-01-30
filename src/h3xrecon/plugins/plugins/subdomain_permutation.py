from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.plugins.puredns import PureDNSPlugin
from h3xrecon.plugins.helper import send_domain_data, is_wildcard
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
        target_wildcard, target_wildcard_type = await is_wildcard(params.get("target", {}))
        if target_wildcard:
            logger.info(f"JOB SKIPPED: Target {params.get("target", {})} is a wildcard domain (Record type: {target_wildcard_type.replace("wildcard_","")}), skipping subdomain permutation processing.")
            return
        parent_domain = ".".join(params.get("target", {}).split(".")[1:])
        parent_wildcard, parent_wildcard_type = await is_wildcard(parent_domain)
        if parent_wildcard:
            logger.debug(f"Parent domain {parent_domain} is a wildcard domain (Record type: {parent_wildcard_type.replace("wildcard_","")}), permutation list will be processed accordingly")
        logger.debug(f"Running {self.name} on {params.get("target", {})}")
        
        wordlist = params.get("wordlist", "/app/Worker/files/permutations.txt")
        if not wordlist:
            wordlist = "/app/Worker/files/permutations.txt"
        if not os.path.exists(wordlist):
            logger.error(f"Wordlist {wordlist} not found")
            return
        logger.debug(f"Using permutation file {wordlist}")
        command = f"echo \"{params.get("target", {})}\" > /tmp/gotator_input.txt && gotator -sub /tmp/gotator_input.txt -perm {wordlist} -depth 1 -numbers 10 -mindup -adv"
        logger.debug(f"Running command {command}")
        to_test = self._create_subprocess_shell_sync(command).splitlines()
        if parent_wildcard:
            to_test = [t for t in to_test if t.endswith(f".{params.get('target', '')}")]
        message = {
            "target": params.get("target", {}),
            "to_test": to_test,
            "target_wildcard": target_wildcard,
            "parent_wildcard": parent_wildcard,
            "parent_domain": parent_domain
        }
        logger.debug(f"Publishing message: {message}")
        yield message

    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:
            # Send the target and parent domain to data worker with the wildcard status
            await send_domain_data(
                qm=qm,
                data=output_msg.get("data").get("target"),
                execution_id=output_msg.get('execution_id'),
                program_id=output_msg.get('program_id'),
                attributes={
                    "is_catchall": output_msg.get("data", {}).get("target_wildcard")
                },
                trigger_new_jobs=output_msg.get('trigger_new_jobs', True)
            )
            await send_domain_data(
                qm=qm,
                data=output_msg.get("data").get("parent_domain"),
                execution_id=output_msg.get('execution_id'),
                program_id=output_msg.get('program_id'),
                attributes={
                    "is_catchall": output_msg.get("data", {}).get("parent_wildcard")
                },
                trigger_new_jobs=output_msg.get('trigger_new_jobs', True)
            )
            # Dispatch puredns and dnsx jobs for the subdomains to test
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
