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

## Deploying to remote servers

### Set Ansible inventory

Set the inventory file in src/ansible/hosts.yaml to point to your servers.

```yaml
all:
  vars:
    h3xrecon_base_directory: /home/h3x/data/projects/h3xrecon # Where is the project cloned on the server
    h3xrecon_target_directory: /home/{{ ansible_user }}/h3xrecon # Where the project will be deployed on the server
    h3xrecon_timezone: America/Montreal

  ## Hosts Definitions
  hosts: {}
    

## Processor Host Group
## Those hosts will run the database, msgbroker and cache components
## Those hosts will also be the Docker Swarm managers
processor:
  vars:
    h3xrecon_role: processor
  hosts:
    recon:
      ansible_host: x.x.x.x
      ansible_user: username
      ansible_ssh_private_key: "{{ PROCESSOR_PRIVATE_KEY }}"
      h3xrecon_dockercompose_pkg: docker-compose-plugin

## Workers Hosts Group
workers:
  vars:
    h3xrecon_role: worker
    h3xrecon_dockercompose_pkg: docker-compose-v2
  hosts:
    vps2:
      ansible_host: y.y.y.y
      ansible_user: username
      ansible_ssh_private_key_file: /path/to/ansible.key
      ansible_ssh_extra_args: '-o StrictHostKeyChecking=no'
```

### Configure the nodes

This playbook will install prerequisites and docker on the nodes as well as configure the Docker Swarm cluster.

```bash
ansible-playbook -i src/ansible/hosts.yaml src/ansible/setup_nodes.yaml
```

### Deploy the project

This playbook will deploy the docker stack on the cluster

```bash
ansible-playbook -i src/ansible/hosts.yaml src/ansible/deploy_h3xrecon_stack.yaml
```
