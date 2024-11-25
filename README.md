# H3XRecon

[![PyPI - Version](https://img.shields.io/pypi/v/h3xrecon.svg)](https://pypi.org/project/h3xrecon)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/h3xrecon.svg)](https://pypi.org/project/h3xrecon)

-----

<p align="center">
  <img src="docs/assets/logo.png" alt="H3XRecon Logo" width="200"/>
</p>

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

## 💻 Getting Started (Docker Swarm)

Please refer to the [Docker Swarm README](docker_swarm/README.md) for more information on how to setup the project using Docker Swarm.

## 💻 Getting Started (Local Docker Compose)

### 1. Clone the repository:

```bash
git clone https://github.com/h3xitsec/h3xrecon.git
cd h3xrecon
```

### 2. Start the compose stack

```bash
docker compose up -d
docker compose logs -f
```

### 3. Pull the cli docker image and setup the configuration file

```bash
# Pull the image
docker pull ghcr.io/h3xitsec/h3xrecon_cli:v0.0.3

# Create the configuration file
cat << EOF > ~/.h3xrecon/config.yaml
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "h3xrecon",
    "user": "h3xrecon",
    "password": "h3xrecon"
  },
  "nats": {
    "host": "localhost",
    "port": 4222
  },
  "logging": {
    "level": "DEBUG",
    "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> - <level>{message}</level>"
  }
}
EOF

# Create a shell alias for the h3xrecon command
alias h3xrecon="docker run --network=host --rm -it -v ~/.h3xrecon:/root/.h3xrecon ghcr.io/h3xitsec/h3xrecon_cli:v0.0.3"
```

### 4. Start using it !

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

Alternatively, you can install the h3xrecon client as a python module and use it directly:

```bash
python -m venv venv
pip install git+https://github.com/h3xitsec/h3xrecon-cli.git
```

For more information on the commands, please refer to the [CLI Documentation](docs/cli.md).

### 5. Scaling the workers

Hot scaling the workers is as simple as running the following command:

```bash
compose scale worker=<number_of_workers>
```

Alternatively, you can set the number of workers in the .env.local file and restart the compose stack.

```bash
# Edit the .env.compose file to set the number of workers
H3XRECON_WORKERS_COUNT=<number_of_workers>
```

## 📊 Monitoring Dashboards

### Grafana
- **URL**: `http://<grafana-host>:3000`
- **Features**:
  - Real-time log aggregation
  - Service performance metrics
  - Custom reconnaissance dashboards

## 📖 Documentation

For detailed usage instructions and configuration options, please refer to the [CLI Documentation](src/h3xrecon/cli/README.md).

## License

`h3xrecon` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
