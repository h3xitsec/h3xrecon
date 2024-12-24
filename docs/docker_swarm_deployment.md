# 🌐 Docker Swarm Deployment

This guide explains how to deploy H3XRecon on a Docker Swarm cluster using Ansible for automation.

## Overview

H3XRecon's Docker Swarm deployment:
- Uses Ansible for automated cluster setup and deployment
- Supports Tailscale for secure node communication (optional)
- Provides scalable worker deployment
- Includes monitoring and logging setup

## Suggested Infrastructure

- **Processor Node**: 1 instance (4 vCPUs, 8GB RAM minimum)
  - Runs core services (database, message broker, processors)
  - Can be hosted on your local network
  
- **Worker Nodes**: 4+ instances (2 vCPUs, 4GB RAM each minimum)
  - Runs reconnaissance tasks
  - Should have public IP addresses
  - Can be scaled horizontally

### Cloud Provider Recommendations

You can use [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) which provides:
- 4 ARM-based instances
- Each with 24GB RAM and 4 OCPUs
- Always Free service
- Public IP addresses included

![Oracle Cloud Free Tier](../docs/assets/oci_free_tier.png)

## Setup

### 1. Install Ansible requirements

```bash
# Source the local environment variables (see .env.local.sh.example)
source ./.env.local.sh

# Install python-venv from your package manager
apt update && apt install python3-venv # Debian/Ubuntu

python -m venv h3xrecon_venv
source h3xrecon_venv/bin/activate
pip install --upgrade pip
pip install ansible
```

### 2. Configure Ansible Inventory

Create your inventory file based on the example at `docker_swarm/ansible/hosts.yaml.example` or the example below:

The environment variables sourced at previous step set Ansible's default inventory file to `docker_swarm/ansible/hosts.yaml`.

If you want to use a different inventory file, you can set the `ANSIBLE_INVENTORY` environment variable to the path of your inventory file or use the `-i` flag when running the ansible commands.

```yaml:docker_swarm/ansible/hosts.yaml
all:
  vars:
    h3xrecon_base_directory: ./
    h3xrecon_target_directory: /home/{{ ansible_user }}/h3xrecon/
    h3xrecon_timezone: America/Montreal
    h3xrecon_swarm_mode: tailscale # This is used to set the swarm communicationmode to tailscale or lan

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

### 3. Set the communication layer

You can use Tailscale as a communication layer between the nodes so there is no need to setup a VPN or forward ports but this step is optional.

#### Using Tailscale

If you want to use Tailscale, you need to set up a free Tailscale account and create an Auth Key. Refer to the [Tailscale Documentation](https://tailscale.com/kb/1204/auth-keys/) for more information.

First, copy the example vault file from `docker_swarm/ansible/vaults/tailscale_vault.yaml.example` to `docker_swarm/ansible/vaults/tailscale_vault.yaml`

Then you need to paste the Auth Key in the `docker_swarm/ansible/vaults/tailscale_vault.yaml` file.

Lastly, you need to encrypt the vault using the following command:

```bash
ansible-vault encrypt docker_swarm/ansible/vaults/tailscale_vault.yaml
```

and paste the vault password in `docker_swarm/ansible/.vaultpass` file.

You also need to make sure the `h3xrecon_swarm_mode` variable is set to "tailscale" in the `hosts.yaml`'s `all` host group.

Depending on your setup, you might need to install Tailscale on the computer from which you will operate H3xRecon to be able to communicate with the processor node.

#### Using another communication layer

If you prefer to use another communication layer, such as an already existing VPN or simply run the stack on a local network, set the `h3xrecon_swarm_mode` variable to `lan` in your `hosts.yaml` file.

Note that there is no need for the worker nodes to be able to communicate with each other, only the processor node will be in charge of sending the tasks to the workers.

### 4. Configure Nodes

Install prerequisites and set up Docker Swarm cluster:

```bash
# This playbook will do the basic setup of the nodes
ansible-playbook ansible/setup_nodes.yaml

# This playbook will setup the docker swarm cluster
ansible-playbook ansible/setup_docker_swarm.yaml

# Validate the docker swarm cluster. This playbook will create a test service to make sure the cluster is working properly.
ansible-playbook ansible/validate_docker_swarm.yaml
```

### 5. Deploy Stack

Deploy the H3XRecon stack to the cluster:

```bash
ansible-playbook ansible/deploy_h3xrecon_stack.yaml
```

## Maintenance and operations

### Adding worker nodes afterwards

Adding worker nodes to the cluster is as simple as adding them to the `workers` host group in the `hosts.yaml` file and run the playbooks from step 4 again.

### Refresh the stack with lastest images

Simply run the `deploy_h3xrecon_stack.yaml` playbook to force the stack to pull the latest images and redeploy the services.

```bash
ansible-playbook ansible/deploy_h3xrecon_stack.yaml
```
