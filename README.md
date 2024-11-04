# H3XRecon

H3XRecon is a powerful reconnaissance tool designed to automate various tasks related to domain and IP address analysis. It leverages multiple plugins to perform tasks such as subdomain discovery, DNS resolution, HTTP testing, and more. The architecture is built around a worker model that allows for easy integration of new plugins, making it highly extensible and adaptable to various reconnaissance needs.

## Features

- **Subdomain Discovery**: Utilize plugins like `subfinder` and `ctfr` to find subdomains associated with a target domain.
- **DNS Resolution**: Resolve domains to their respective IP addresses and gather additional DNS records.
- **HTTP Testing**: Test HTTP endpoints for various attributes, including status codes and content types.
- **Reverse IP Lookup**: Discover domains associated with a given IP address.
- **Catch-All Domain Testing**: Check if a domain is a catch-all by attempting to resolve random subdomains.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.9 or higher
- Redis
- NATS server

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/h3xrecon.git
   cd h3xrecon
   ```

2. Build and start the services using Docker Compose:
   ```bash
   docker-compose up --build
   ```

3. Ensure all services are running correctly.

### Usage

To execute a function, publish a message to the NATS server. For example, to resolve a domain:

```bash
nats pub function.execute '{ "function": "resolve_domain", "program_id": 1, "params": { "target": "example.com" }}'
```

## Plugin Architecture

H3XRecon supports a variety of plugins that can be easily integrated into the worker. Each plugin must inherit from the `ReconPlugin` base class and implement the `execute` method.

### Plugin Types

1. **String Output Plugin**: A plugin that yields string outputs.
   ```python
   from typing import AsyncGenerator, Dict, Any
   from plugins.base import ReconPlugin
   from loguru import logger

   class ExampleStringPlugin(ReconPlugin):
       @property
       def name(self) -> str:
           return "example_string_plugin"

       async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
           logger.info(f"Running {self.name} on {target}")
           yield {"output": f"Processed target: {target}"}
   ```

2. **JSON Output Plugin**: A plugin that yields JSON formatted outputs.
   ```python
   from typing import AsyncGenerator, Dict, Any
   from plugins.base import ReconPlugin
   from loguru import logger
   import json

   class ExampleJsonPlugin(ReconPlugin):
       @property
       def name(self) -> str:
           return "example_json_plugin"

       async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
           logger.info(f"Running {self.name} on {target}")
           result = {"target": target, "status": "success"}
           yield result
   ```

3. **Bash Command Plugin**: A plugin that executes a bash command and yields the output.
   ```python
   from typing import AsyncGenerator, Dict, Any
   from plugins.base import ReconPlugin
   from loguru import logger
   import asyncio

   class ExampleBashPlugin(ReconPlugin):
       @property
       def name(self) -> str:
           return "example_bash_plugin"

       async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
           logger.info(f"Running {self.name} on {target}")
           command = f"echo 'Running command on {target}'"
           process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE)
           output = await process.stdout.read()
           yield {"output": output.decode().strip()}
   ```

4. **Python Command Plugin**: A plugin that executes Python code directly.
   ```python
   from typing import AsyncGenerator, Dict, Any
   from plugins.base import ReconPlugin
   from loguru import logger

   class ExamplePythonPlugin(ReconPlugin):
       @property
       def name(self) -> str:
           return "example_python_plugin"

       async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
           logger.info(f"Running {self.name} on {target}")
           result = {"message": f"Hello from {target}"}
           yield result
   ```

### Integrating New Plugins

To integrate a new plugin:

1. Create a new Python file in the `Worker/plugins` directory.
2. Implement the plugin class as shown in the examples above.
3. Ensure the class inherits from `ReconPlugin` and implements the `execute` method.
4. The plugin will be automatically loaded by the `FunctionExecutor` when the worker starts.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Thanks to the open-source community for the various tools and libraries used in this project.
