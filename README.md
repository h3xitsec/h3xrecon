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

2. Build the local images (optional, you can also pull the images from the ghcr.io registry, see section 4):
```bash
./build.sh
```

3. Configure the environment:
```bash
# This will set all the requirement environment variables for the local stack and add the bin directory to the PATH
source localenv.sh
```

4. Start (and manage) the services:

The `compose` script is a wrapper around `docker compose` that simplifies the usage of the local stack.

See the [compose wrapper documentation](docs/compose_wrapper.md) for more information.

TLDR:
```bash
compose [local|public] [docker compose options]
```

5. Start using it

Source the localenv.sh script to set the environment variables and alias for h3xrecon client's docker image

```bash
. ./localenv.sh
```

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
git clone https://github.com/h3xitsec/h3xrecon-cli.git
cd h3xrecon-cli
pip install .
```

For more information on the commands, please refer to the [CLI Documentation](docs/cli.md).

6. Scaling the workers

Hot scaling the workers is as simple as running the following command:

```bash
compose scale worker=<number_of_workers>
```

Alternatively, you can set the number of workers in the .env.local file and restart the compose stack.

```bash
# Edit the .env.compose file to set the number of workers
H3XRECON_WORKERS_COUNT=<number_of_workers>
```

### 🌐 Remote Deployment

Ansible is used to deploy the H3XRecon stack to a remote Docker Swarm cluster.

It setup the whole docker swarm cluster using Tailscale as a communication layer between the nodes.

#### 1. Install Ansible requirements

```bash
# Install python-venv from your package manager
apt update && apt install python3-venv # Debian/Ubuntu

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. Configure Ansible Inventory

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

#### 3. Configure Nodes

Install prerequisites and set up Docker Swarm cluster:

```bash
# Will do the basic setup of the nodes and install docker and setup a docker swarm cluster
ansible-playbook ansible/setup_nodes.yaml
```

#### 4. Deploy Stack

Deploy the H3XRecon stack to the cluster:

```bash
ansible-playbook ansible/deploy_h3xrecon_stack.yaml
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
