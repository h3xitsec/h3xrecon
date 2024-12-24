# 🔌 H3XRecon Plugin System

## Overview

H3XRecon's plugin system provides a flexible and extensible framework for implementing various reconnaissance tasks. Each plugin is a self-contained module that inherits from the `ReconPlugin` base class and implements specific reconnaissance functionality.

## Plugin Architecture

### Base Class

All plugins inherit from the `ReconPlugin` abstract base class:

```python
from typing import AsyncGenerator, Dict, Any
from abc import ABC, abstractmethod

class ReconPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the plugin name"""
        pass

    @abstractmethod
    async def execute(self, target: str, program_id: int = None, execution_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute the reconnaissance task"""
        pass

    @abstractmethod
    async def process_output(self, output_msg: Dict[str, Any], db = None) -> Dict[str, Any]:
        """Process and store the task output"""
        pass
```

### Plugin Categories

#### 1. Subdomain Discovery
- [FindSubdomainsPlugin](#findsubdomainsplugin): Meta-plugin for subdomain discovery
- [SubdomainPermutation](#subdomainpermutation): Generates and tests subdomain variations
- [FindSubdomainsSubfinder](#findsubdomainssubfinder): Uses Subfinder tool
- [FindSubdomainsCTFR](#findsubdomainsctfr): Uses Certificate Transparency logs

#### 2. Network Reconnaissance
- [PortScan](#portscan): Port scanning and service detection
- [TestHTTP](#testhttp): HTTP endpoint testing
- [CIDRIntel](#cidrintel): CIDR range intelligence gathering
- [ExpandCIDR](#expandcidr): CIDR expansion to individual IPs

#### 3. DNS Operations
- [ResolveDomain](#resolvedomain): Domain to IP resolution
- [TestDomainCatchall](#testdomaincatchall): DNS catchall detection
- [ReverseResolveIP](#reverseresolveip): IP to domain resolution

## Plugin Development Guide

### 1. Creating a New Plugin

1. Create a new file in `src/h3xrecon/plugins/plugins/`
2. Inherit from `ReconPlugin`
3. Implement required methods

Example:
```python
from h3xrecon.plugins import ReconPlugin
from h3xrecon.core import QueueManager
from loguru import logger

class CustomPlugin(ReconPlugin):
    @property
    def name(self) -> str:
        return "custom_plugin"

    async def execute(self, target: str, program_id: int = None, execution_id: str = None):
        logger.info(f"Running {self.name} on {target}")
        # Implement reconnaissance logic here
        yield {"status": "success", "data": "example output"}

    async def process_output(self, output_msg: Dict[str, Any], db = None):
        # Process and store results
        message = {
            "program_id": output_msg.get('program_id'),
            "data_type": "custom_data",
            "data": output_msg.get('output', {})
        }
        await self.qm.publish_message("recon.data", "RECON_DATA", message)
```

### 2. Best Practices

1. **Error Handling**
   - Use try-except blocks for external tool execution
   - Log errors with appropriate severity
   - Return meaningful error messages

2. **Resource Management**
   - Clean up temporary files
   - Use async context managers
   - Implement timeouts for long-running operations

3. **Output Format**
   - Use consistent data structures
   - Include metadata (timestamps, tool versions)
   - Follow the schema expected by the data processor

### 3. Testing

1. Create unit tests in `tests/plugins/`
2. Test error conditions
3. Mock external dependencies
4. Verify output format

Example test:
```python
import pytest
from h3xrecon.plugins.plugins.custom_plugin import CustomPlugin

@pytest.mark.asyncio
async def test_custom_plugin():
    plugin = CustomPlugin()
    results = []
    async for result in plugin.execute("example.com"):
        results.append(result)
    assert len(results) > 0
    assert results[0]["status"] == "success"
```

## Integration with Core Components

### Worker Integration

The Worker component:
1. Loads plugins dynamically
2. Maps function names to plugins
3. Executes plugin functions based on job messages
4. Handles plugin execution errors

### JobProcessor Integration

The JobProcessor:
1. Validates plugin output
2. Triggers dependent jobs
3. Updates job status
4. Manages plugin execution flow

## Troubleshooting

Common issues and solutions:

1. **Plugin Not Loading**
   - Check file naming
   - Verify class inheritance
   - Check for syntax errors

2. **Execution Errors**
   - Check external tool dependencies
   - Verify input parameters
   - Check log files

3. **Output Processing Issues**
   - Verify message format
   - Check queue connectivity
   - Validate data types

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add your plugin
4. Add tests
5. Submit a pull request

For detailed contribution guidelines, see [CONTRIBUTING.md](../../CONTRIBUTING.md).
