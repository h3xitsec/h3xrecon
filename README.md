# h3xrecon

h3xrecon is a bug bounty reconnaissance automation tool.

## Installation for local development

### Prerequisites

- Docker
- Docker Compose v2 (docker compose, not docker-compose)
- Python 3.11+ with venv and pip

### Setup

```bash
git clone https://github.com/h3xitsec/h3xrecon.git
cd h3xrecon
python3 -m venv venv
source venv/bin/activate
pip install .
```

### Start Docker Compose services

```bash
docker compose -f src/docker/docker-compose.local.yaml up -d
```
