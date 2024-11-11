# H3XRecon

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

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`, not `docker-compose`)
- Python 3.11+
- Ansible 2.9+ (for remote deployment)

## 💻 Local Development Setup

1. Clone the repository:
```bash
git clone https://github.com/h3xitsec/h3xrecon.git
cd h3xrecon
```

2. Create and activate Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

4. Configure development environment:
```bash
source devenv.sh
```

### Managing Docker Services

```bash
# Start services and view logs
docker compose up

# Run in detached mode
docker compose up -d

# View logs
docker compose logs -f [service_name]

# Stop all services
docker compose down
```

## 🌐 Remote Deployment

### 1. Configure Ansible Inventory

Create your inventory file at `src/ansible/hosts.yaml`. Example configuration:

```yaml:src/ansible/hosts.yaml
startLine: 1
endLine: 85
```

### 2. Configure Nodes

Install prerequisites and set up Docker Swarm cluster:

```bash
ansible-playbook -i src/ansible/hosts.yaml src/ansible/setup_nodes.yaml
```

### 3. Deploy Stack

Deploy the H3XRecon stack to the cluster:

```bash
ansible-playbook -i src/ansible/hosts.yaml src/ansible/deploy_h3xrecon_stack.yaml
```

## 📊 Monitoring Dashboards

### Grafana
- **URL**: `http://<grafana-host>:3000`
- **Default Credentials**: 
  - Username: `admin`
  - Password: `admin`
- **Features**:
  - Real-time log aggregation
  - Service performance metrics
  - Custom reconnaissance dashboards

### Docker Swarm Dashboard
- **URL**: `http://<swarm-manager-host>:8080`
- **Features**:
  - Service health monitoring
  - Container management
  - Resource utilization metrics

## 📖 Documentation

For detailed usage instructions and configuration options, please refer to the [CLI Documentation](src/h3xrecon/cli/README.md).
