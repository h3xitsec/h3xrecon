#!/usr/bin/env bash

# Change to the ansible directory
cd src/ansible || exit 1

# Run the setup nodes playbook
#ansible-playbook setup_nodes.yaml

#export ANSIBLE_STDOUT_CALLBACK=debug

#ansible-playbook validate_docker_swarm.yaml

# Run the h3xrecon stack deployment playbook
ansible-playbook deploy_h3xrecon_stack.yaml

# Return to original directory
cd - > /dev/null
