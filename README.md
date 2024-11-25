# H3XRecon

[![PyPI - Version](https://img.shields.io/pypi/v/h3xrecon.svg)](https://pypi.org/project/h3xrecon)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/h3xrecon.svg)](https://pypi.org/project/h3xrecon)

-----

H3XRecon is a powerful bug bounty reconnaissance automation tool designed to streamline and automate the reconnaissance phase of security assessments. It provides a distributed architecture for efficient scanning and data processing.

## 🚀 Features

- Distributed reconnaissance architecture using Docker Swarm
- Real-time log aggregation and visualization with Grafana
- Modular plugin system for custom reconnaissance tools
- Centralized data processing and storage
- Built-in scope management and filtering
- Bug Bounty program management with scope management

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`, not `docker-compose`)
- Python 3.11+
- Ansible 2.9+ (for remote deployment)

## Recon Workflow

<p align="center">
  <img src="docs/assets/h3xrecon_workflow.png" alt="H3XRecon Workflow"/>
</p>

## Credits

The client part of the project is inspired from the [BBRF client](https://github.com/honoki/bbrf-client) by @honoki. This is what I was using before I started this project, so I made it work in the same way,

## Getting Started

### 💻 Local Docker Compose

Please refer to the [Docker Compose Deployment](docs/docker_compose_deployment.md) for more information on how to setup the project using Docker Compose.

OR

### � Docker Swarm

Please refer to the [Docker Swarm Deployment](docs/docker_swarm_deployment.md) for more information on how to setup the project using Docker Swarm.

### 📦 Install the h3xrecon client

Refer to the [Client Documentation](docs/client.md) for more information on how to install the h3xrecon client.

### 🚀 Start using it !

Setup your first program

```bash
# Create a new program
h3xrecon program add program_name
# Add a scope to the program
h3xrecon -p program_name config add scope ".*example.com"
# Add a cidr to the program
h3xrecon -p program_name config add cidr "1.2.3.4/24"
# Send a job to the program
h3xrecon -p program_name sendjob resolve_domain example.com
# View data
h3xrecon -p program_name list domains/urls/ips/services
```

For more information on the commands, please refer to the [Client Documentation](docs/client.md).

## 📊 Monitoring Dashboards

### Grafana
- **URL**: `http://<processor host>:3000`
- **Features**:
  - Real-time log aggregation
  - Service performance metrics
  - Custom reconnaissance dashboards

## License

`h3xrecon` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
