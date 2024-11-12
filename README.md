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
- Bug Bounty program management with scope management

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`, not `docker-compose`)
- Python 3.11+
- Ansible 2.9+ (for remote deployment)

## 💻 Getting Started

### Local Docker Compose Option

1. Clone the repository:
```bash
git clone https://github.com/h3xitsec/h3xrecon.git
cd h3xrecon
```

2. Build the local images:
```bash
./build.sh
```

3. Configure the environment:
```bash
# This will set all the requirement environment variables for the local stack
source localenv.sh
```

4. Start (and manage) the services:

The `compose.sh` script is a wrapper around `docker compose` that simplifies the usage of the local stack.

See the [compose wrapper documentation](docs/compose_wrapper.md) for more information.

TLDR:
```bash
./compose.sh [local|public] [docker compose options]
```

### 🌐 Remote Deployment

#### 1. Configure Ansible Inventory

Create your inventory file at `src/ansible/hosts.yaml`. Example configuration:

```yaml:/ansible/hosts.yaml
all:
  vars:
    h3xrecon_base_directory: ./
    h3xrecon_target_directory: /home/{{ ansible_user }}/h3xrecon/
    h3xrecon_timezone: America/Montreal

  # No hosts defined by default
  hosts: {}
    

## Processor Host Group
## Those will be used to run the message broker, database, caching and processor services
processor:
  vars:
    H3XRECON_SWARM_ROLE: processor # This is used to set the node label in docker swarm
  hosts:
    processor1:
      ansible_host: 1.1.1.1
      ansible_user: username
      ansible_ssh_private_key_file: /path/to/private/key
      h3xrecon_dockercompose_pkg: docker-compose-plugin # Not all distros have the same package name so we set it here

## Workers Hosts Group
## Those will be used to run the worker services
workers:
  vars:
    H3XRECON_SWARM_ROLE: worker # This is used to set the node label in docker swarm
  hosts:
    worker1:
      ansible_host: 2.2.2.1
      ansible_user: username
      ansible_ssh_private_key_file: /path/to/private/key
      ansible_ssh_extra_args: '-o IdentitiesOnly=yes -o StrictHostKeyChecking=no'

    worker2:
      ansible_host: 2.2.2.2
      ansible_user: username
      ansible_ssh_private_key_file: /path/to/private/key
      ansible_ssh_extra_args: '-o IdentitiesOnly=yes -o StrictHostKeyChecking=no'

    worker3:
      ansible_host: 2.2.2.3
      ansible_user: username
      ansible_ssh_private_key_file: /path/to/private/key
      ansible_ssh_extra_args: '-o IdentitiesOnly=yes -o StrictHostKeyChecking=no'

    worker4:
      ansible_host: 2.2.2.4
      ansible_user: username
      ansible_ssh_private_key_file: /path/to/private/key
      ansible_ssh_extra_args: '-o IdentitiesOnly=yes -o StrictHostKeyChecking=no'
```

#### 2. Configure Nodes

Install prerequisites and set up Docker Swarm cluster:

```bash
ansible-playbook -i src/ansible/hosts.yaml src/ansible/setup_nodes.yaml
```

#### 3. Deploy Stack

Deploy the H3XRecon stack to the cluster:

```bash
ansible-playbook -i src/ansible/hosts.yaml src/ansible/deploy_h3xrecon_stack.yaml
```

## Recon Workflow

<p align="center">
  <img src="docs/assets/h3xrecon_workflow.png" alt="H3XRecon Workflow"/>
</p>


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
