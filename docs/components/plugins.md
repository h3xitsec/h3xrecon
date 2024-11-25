# H3XRecon Plugin Documentation

## Table of Contents

- [Introduction](#introduction)
- [Plugin Overview](#plugin-overview)
  - [Core Plugins](#core-plugins)
    - [FindSubdomainsPlugin](#findsubdomainsplugin)
    - [SubdomainPermutation](#subdomainpermutation)
    - [FindSubdomainsSubfinder](#findsubdomainssubfinder)
    - [FindSubdomainsCTFR](#findsubdomainsctfr)
  - [Network Reconnaissance Plugins](#network-reconnaissance-plugins)
    - [PortScan](#portscan)
    - [TestHTTP](#testhttp)
    - [CIDRIntel](#cidrintel)
    - [ExpandCIDR](#expandcidr)
  - [DNS and Resolution Plugins](#dns-and-resolution-plugins)
    - [ResolveDomain](#resolvedomain)
    - [TestDomainCatchall](#testdomaincatchall)
    - [ReverseResolveIP](#reverseresolveip)
- [Components Utilizing Plugins](#components-utilizing-plugins)
  - [Worker](#worker)
  - [JobProcessor](#jobprocessor)
- [Additional Sections](#additional-sections)
  - [Conclusion](#conclusion)
  - [Quick Reference](#quick-reference)
  - [Troubleshooting](#troubleshooting)
  - [Contribution Guidelines](#contribution-guidelines)
- [Supplementary Information](#supplementary-information)
  - [Acknowledgements](#acknowledgements)
  - [License](#license)
  - [Contact](#contact)

## Introduction

H3XRecon is a reconnaissance framework designed to automate various reconnaissance tasks through a modular plugin system. Each plugin encapsulates specific reconnaissance functionalities, enabling extensibility and ease of maintenance. This documentation provides an overview of the available plugins, their roles, functionalities, and how they integrate with the core components of H3XRecon: the Worker and JobProcessor.

## Plugin Overview

H3XRecon's plugin system is built around the `ReconPlugin` abstract base class, ensuring consistency across all plugins. Each plugin inherits from this base class and implements the required methods to perform specific reconnaissance tasks.

## Components Utilizing Plugins

### Worker

The `Worker` component is responsible for executing reconnaissance functions dispatched as jobs. It interacts closely with the plugins to perform specific tasks based on incoming job messages.

**Key Responsibilities:**
- Fetches job messages from the `FUNCTION_EXECUTE` stream.
- Executes the corresponding plugin functions based on the `function` field in the job message.
- Publishes the results of the execution to the `FUNCTION_OUTPUT` stream.

**Integration with Plugins:**
- Initializes a `FunctionExecutor` which maps function names to their corresponding plugin execute methods.
- Ensures that each plugin is loaded and its execute method is available for job execution.

**Relevant Code:**

## Example Usage

Below is an example of how to integrate a new plugin into the H3XRecon system.

```python:src/h3xrecon/plugins/plugins/example_plugin.py
from typing import AsyncGenerator, Dict, Any
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import QueueManager
from loguru import logger
import asyncio
import json

class ExamplePlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return "example_plugin"

    async def execute(self, target: str, program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {target}")
        # Example command execution
        command = f"echo 'Example execution on {target}'"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        async for output in self.read_subprocess_output(process):
            yield {"message": output}
        await process.wait()

    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        self.config = Config()
        self.qm = QueueManager(self.config.nats)
        message = {
            "program_id": output_msg.get('program_id'),
            "data_type": "message", 
            "data": [output_msg.get('output', {}).get('message')]
        }
        await self.qm.publish_message(subject="recon.data", stream="RECON_DATA", message=message)
```

### FindSubdomainsPlugin

**Description:**  
The `FindSubdomainsPlugin` is a meta-plugin that triggers multiple subdomain discovery tools. It orchestrates the execution of various subdomain enumeration techniques to gather comprehensive subdomain information for a given target.

**Functionality:**
- Dispatches jobs to multiple subdomain discovery tools such as `find_subdomains_subfinder` and `find_subdomains_ctfr`.
- Yields dispatched job information to initiate subdomain discovery processes.

**Key Methods:**
- `execute`: Dispatches subdomain discovery jobs.
- `send_job`: Sends a job to the worker using `QueueManager`.
- `process_output`: Processes the output from subdomain discovery tools and dispatches further tasks based on the results.

### SubdomainPermutation

**Description:**  
The `SubdomainPermutation` plugin generates permutations of subdomains based on the target's domain to discover potential hidden subdomains.

**Functionality:**
- Generates permutations using predefined rules and dispatches them for reverse DNS resolution.
- Filters results based on DNS catchall detection to avoid unnecessary processing.

**Key Methods:**
- `execute`: Generates subdomain permutations and yields them as jobs.
- `process_output`: Determines if the target domain is a DNS catchall and processes the generated permutations accordingly.

### FindSubdomainsSubfinder

**Description:**  
The `FindSubdomainsSubfinder` plugin leverages the `subfinder` tool to discover subdomains of a target domain.

**Functionality:**
- Executes the `subfinder` command to enumerate subdomains.
- Parses the output and yields discovered subdomains.

**Key Methods:**
- `execute`: Runs the `subfinder` command and yields discovered subdomains.
- `process_output`: Publishes the discovered subdomains to the recon data queue for further processing.


### PortScan

**Description:**  
The `PortScan` plugin performs a comprehensive port scan on the target IP to identify open ports and services.

**Functionality:**
- Utilizes `nmap` to scan the top 1000 ports on the target.
- Parses the XML output to extract port information and service details.

**Key Methods:**
- `execute`: Executes the `nmap` port scan and yields the scan results.
- `process_output`: Publishes the scan results to the recon data queue for further analysis.


### TestHTTP

**Description:**  
The `TestHTTP` plugin uses the `httpx` tool to perform HTTP testing on discovered URLs.

**Functionality:**
- Executes `httpx` with various parameters to gather detailed HTTP information.
- Parses the JSON output and yields the results.

**Key Methods:**
- `execute`: Runs the `httpx` command and yields the HTTP test results.
- `process_output`: Publishes the HTTP test results and any discovered domains to the recon data queue.


### CIDRIntel

**Description:**  
The `CIDRIntel` plugin gathers intelligence on a given CIDR range by employing the `amass` tool.

**Functionality:**
- Executes `amass intel` to fetch domain and IP information within the specified CIDR range.
- Parses and yields the collected data.

**Key Methods:**
- `execute`: Runs the `amass intel` command and yields the intelligence data.
- `process_output`: Publishes the collected domain and IP information to the recon data queue.


### ResolveDomain

**Description:**  
The `ResolveDomain` plugin resolves domain names to their respective IP addresses using `dnsx`.

**Functionality:**
- Executes a DNS resolution command to obtain A and CNAME records.
- Parses the JSON output and yields the resolved data.

**Key Methods:**
- `execute`: Runs the DNS resolution command and yields the resolved data.
- `process_output`: Publishes the resolved IPs and domains to the recon data queue.


### FindSubdomainsCTFR

**Description:**  
The `FindSubdomainsCTFR` plugin utilizes the CTFR tool to perform subdomain enumeration through Certificate Transparency logs.

**Functionality:**
- Executes the CTFR script to discover subdomains and yields the results.
- Cleans up temporary log files post-execution.

**Key Methods:**
- `execute`: Runs the CTFR tool and yields discovered subdomains.
- `process_output`: Publishes the discovered subdomains to the recon data queue.


### TestDomainCatchall

**Description:**  
The `TestDomainCatchall` plugin checks whether a domain is a DNS catchall, which automatically resolves any subdomain.

**Functionality:**
- Generates a random subdomain and attempts to resolve it.
- Determines if the domain is a catchall based on the resolution results.

**Key Methods:**
- `execute`: Checks for DNS catchall by resolving a random subdomain.
- `process_output`: Publishes the catchall status of the domain to the recon data queue.


### ReverseResolveIP

**Description:**  
The `ReverseResolveIP` plugin performs reverse DNS lookups to identify domains associated with a given IP address.

**Functionality:**
- Executes a reverse DNS resolution command to obtain PTR records.
- Parses and yields the resolved domains.

**Key Methods:**
- `execute`: Runs the reverse DNS resolution command and yields the resolved domain.
- `process_output`: Publishes the resolved domain and associated IP information to the recon data queue.

### ExpandCIDR

**Description:**  
The `ExpandCIDR` plugin expands a CIDR notation into individual IP addresses and dispatches reverse DNS resolution tasks for each IP.

**Functionality:**
- Uses the `prips` tool to list all IPs within the specified CIDR range.
- Dispatches `reverse_resolve_ip` tasks for each IP found.

**Key Methods:**
- `execute`: Expands the CIDR to individual IPs and yields reverse resolution jobs.
- `process_output`: Publishes reverse DNS resolution tasks to the function execution queue.


### ReverseResolveIP

**Description:**  
The `ReverseResolveIP` plugin performs reverse DNS lookups to identify domains associated with a given IP address.

**Functionality:**
- Executes a reverse DNS resolution command to obtain PTR records.
- Parses and yields the resolved domains.

**Key Methods:**
- `execute`: Runs the reverse DNS resolution command and yields the resolved domain.
- `process_output`: Publishes the resolved domain and associated IP information to the recon data queue.

