from typing import AsyncGenerator, Dict, Any, List
from h3xrecon.plugins import ReconPlugin
from h3xrecon.plugins.helper import send_ip_data, send_domain_data, send_dns_data, is_wildcard
from h3xrecon.core.utils import is_valid_hostname
from loguru import logger
import os
import random

FILES_PATH = os.environ.get('H3XRECON_RECON_FILES_PATH')
RESOLVERS_FILE = f"{FILES_PATH}/resolvers.txt"
RESOLVERS_TRUSTED_FILE = f"{FILES_PATH}/resolvers-trusted.txt"
BRUTEFORCE_WORDLIST = f"{FILES_PATH}/subdomains.txt"

class PureDNSPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]
    
    @property
    def timeout(self) -> int:
        """Timeout in seconds for the plugin execution. Default is 300 seconds (5 minutes)."""
        return 30
    
    @property
    def target_types(self) -> List[str]:
        return ["domain"]
    
    def __init__(self, wordlist: str = BRUTEFORCE_WORDLIST):
        self.output = {"resolved": [], "wildcards": [], "mode": None}
        self.run_mode = None
        self.wordlist = wordlist

    async def is_input_valid(self, params: Dict[str, Any]) -> bool:
        return is_valid_hostname(params.get("target", {}))
    
    def clean_tmp_files(self):
        try:
            os.remove("/tmp/puredns.txt")
            os.remove("/tmp/puredns_wildcards.txt")
            os.remove("/tmp/puredns_target.txt")
            os.remove("/tmp/puredns_massdns.txt")
        except FileNotFoundError:
            pass
    
    def read_puredns_output(self):
        """
        Read the puredns output files and update the output dictionary
        """
        logger.debug("Reading puredns output")
        logger.debug(f"Output before: {self.output}")
        output_file_map = {
            "resolved": "/tmp/puredns_massdns.txt",
            "wildcards": "/tmp/puredns_wildcards.txt",
        }
        for file in output_file_map:
            try:
                with open(output_file_map[file], "r") as f:
                    if file not in self.output:
                        self.output[file] = []
                    self.output[file].extend([line.strip() for line in f.readlines() if line.strip()])
            except FileNotFoundError:
                #logger.error(f"File not found: {output_file_map[file]}")
                pass
        # Remove duplicates while preserving order
        self.output["wildcards"] = list(dict.fromkeys(self.output["wildcards"]))
        self.output["resolved"] = list(dict.fromkeys(self.output["resolved"]))
        logger.debug(f"Output after: {self.output}")

    def _get_resolve_command(self, target: str) -> str:
        """
        Generate the puredns resolve command for a given target
        """
        wrapper = f"echo {target} > /tmp/puredns_target.txt"
        return f"{wrapper} && puredns resolve /tmp/puredns_target.txt \
                --resolvers {RESOLVERS_FILE} \
                --resolvers-trusted {RESOLVERS_TRUSTED_FILE} \
                --write-massdns /tmp/puredns_massdns.txt \
                --write-wildcards /tmp/puredns_wildcards.txt \
                --write /tmp/puredns.txt \
                -q"

    def _get_bruteforce_command(self, target: str) -> str:
        """
        Generate the puredns bruteforce command for a given target
        """
        wrapper = f"echo {target} > /tmp/puredns_target.txt"
        return f"{wrapper} && puredns bruteforce {self.wordlist} \
                -d /tmp/puredns_target.txt \
                --resolvers {RESOLVERS_FILE} \
                --resolvers-trusted {RESOLVERS_TRUSTED_FILE} \
                --write-massdns /tmp/puredns_massdns.txt \
                --write-wildcards /tmp/puredns_wildcards.txt \
                --write /tmp/puredns.txt \
                -q"

    def resolve_target(self, target: str):
        """
        Resolve the target with puredns
        """
        # First resolve the target with a random number to test if the target is a wildcard domain
        randomized_subdomain = f"{random.randint(1000000000, 9999999999)}.{target}"
        command = self._get_resolve_command(randomized_subdomain)
        stdout, stderr = self._create_subprocess_shell_sync(command)
        if stderr:
            logger.warning(f"puredns stderr output: {stderr}")
        logger.debug(f"Command output: {stdout}")
        self.read_puredns_output()
        # If the target is a wildcard domain, remove the randomized subdomain from the resolved output
        if target in self.output.get("wildcards", []):
            for record in self.output.get("resolved", []):
                if record.startswith(randomized_subdomain):
                    self.output["resolved"].remove(record)
        # Resolve the actual target
        command = self._get_resolve_command(target)
        stdout, stderr = self._create_subprocess_shell_sync(command)
        if stderr:
            logger.warning(f"puredns stderr output: {stderr}")
        logger.debug(f"Command output: {stdout}")
        self.read_puredns_output()

    
    async def execute(self, params: Dict[str, Any], program_id: int = None, execution_id: str = None, trigger_new_jobs: bool = True, db = None, qm = None) -> AsyncGenerator[Dict[str, Any], None]:
        if not params.get("mode"):
            logger.error("Run mode not specified")
            return
        self.output["mode"] = params.get("mode")
        self.run_mode = params.get("mode")
        self.wordlist = params.get("wordlist", BRUTEFORCE_WORDLIST)
        target = params.get("target", None)
        logger.debug(f"Running {self.name} ({self.run_mode} mode) on {target}")

        
        self.clean_tmp_files()
        
        # Bruteforce mode
        if self.run_mode == "bruteforce":
            if params.get("wordlist"):
                self.wordlist = params.get("wordlist")
            else:
                self.wordlist = BRUTEFORCE_WORDLIST
            if not os.path.exists(self.wordlist):
                logger.error(f"Wordlist {self.wordlist} not found")
                return
            # Check if the target is a wildcard domain
            wildcard, wildcard_type = await is_wildcard(params.get("target", {}))
            if wildcard:
                logger.info(f"JOB SKIPPED: Target {params.get("target", {})} is a wildcard domain (Record type: {wildcard_type.replace("wildcard_","")}), skipping subdomain permutation processing.")
                return
            else:
                logger.debug(f"Domain {target} is not a wildcard domain, proceeding with bruteforce")
                self.clean_tmp_files()
                command = self._get_bruteforce_command(target)
                stdout, stderr = self._create_subprocess_shell_sync(command)
                if stderr:
                    logger.warning(f"puredns bruteforce stderr output: {stderr}")
                logger.debug(f"Command output: {stdout}")
                self.read_puredns_output()
        

        elif self.run_mode == "resolve":
            # Resolve mode
            self.resolve_target(target)
            #self.read_puredns_output()
        
        else:
            raise ValueError(f"Invalid mode: {self.run_mode}")

        logger.debug(f"Output: {self.output}")
        if len(self.output.get("resolved", [])) > 0 or len(self.output.get("wildcards", [])) > 0:
            yield self.output
        
        # Cleanup temporary files
        self.clean_tmp_files()


    async def process_output(self, output_msg: Dict[str, Any], db = None, qm = None) -> Dict[str, Any]:   
        logger.debug(f"Processing output: {output_msg}")
        try:
            self.run_mode = output_msg.get('source', {}).get('params', {}).get('mode', None)
            logger.debug(f"Run mode: {self.run_mode}")
            # Get the raw output data
            data = output_msg.get("data", {})
            resolved = data.get('resolved', [])
            wildcards = data.get('wildcards', [])

            # Filter out subdomains of wildcard domains
            filtered_resolved = []
            for record in resolved:
                parts = record.split(' ')
                if len(parts) != 3:
                    continue
                subdomain = parts[0].rstrip('.')
                is_subdomain_of_wildcard = False
                for wildcard in wildcards:
                    wildcard_domain = wildcard.split(' ')[0].rstrip('.')  # Get domain part from wildcard record
                    if subdomain.endswith(wildcard_domain) and subdomain != wildcard_domain:
                        is_subdomain_of_wildcard = True
                        break
                if not is_subdomain_of_wildcard:
                    filtered_resolved.append(record)
            
            resolved = filtered_resolved            
            
            for record in resolved:
                # Split the record into components
                parts = record.split(' ')
                if len(parts) != 3:
                    logger.warning(f"Invalid record format: {record}")
                    continue
                    
                name = parts[0].rstrip('.')  # Remove trailing dot
                record_type = parts[1]
                value = parts[2]
                logger.debug(f"Name: {name}, Record type: {record_type}, Value: {value}")
                parsed_record = {
                    'hostname': name,
                    'dns_type': record_type,
                    'value': value,
                    'ttl': 0,
                    'dns_class': '?IN?',
                    'target_domain': output_msg.get('source', {}).get('params', {}).get('target')
                }
                logger.debug(f"Parsed record: {parsed_record}")
                # Send DNS record data
                await send_dns_data(
                    qm=qm,
                    data=parsed_record,
                    program_id=output_msg.get('program_id'),
                    trigger_new_jobs=output_msg.get('trigger_new_jobs', False),
                    execution_id=output_msg.get('execution_id'),
                    response_id=output_msg.get('response_id')
                )
                logger.debug(f"Sent DNS record {parsed_record} to data processor queue")

                # If it's an A record, send IP data
                if record_type == 'A':
                    await send_ip_data(
                        qm=qm,
                        data=value,
                        program_id=output_msg.get('program_id'),
                        trigger_new_jobs=output_msg.get('trigger_new_jobs', True),
                        execution_id=output_msg.get('execution_id'),
                        response_id=output_msg.get('response_id')
                    )
                    logger.debug(f"Sent IP {value} to data processor queue")

                # Send domain data
                await send_domain_data(
                    qm=qm,
                    data=name,
                    execution_id=output_msg.get('execution_id'),
                    response_id=output_msg.get('response_id'),
                    program_id=output_msg.get('program_id'),
                    attributes={
                        "cnames": [value] if record_type == 'CNAME' else None,
                        "ips": [value] if record_type == 'A' else None,
                        "is_catchall": name in wildcards
                    },
                    trigger_new_jobs=output_msg.get('trigger_new_jobs', True)
                )
                logger.debug(f"Sent domain {name} to data processor queue")

        except Exception as e:
            logger.error(f"Error in process_output: {str(e)}")
            logger.exception(e)