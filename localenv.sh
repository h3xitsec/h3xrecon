#!/bin/bash

# Environment variables
## reconh3x specific variables
export H3XRECON_DB_USER=h3xrecon
export H3XRECON_DB_NAME=h3xrecon
export H3XRECON_DB_HOST=$H3XRECON_PROCESSOR_HOST
export H3XRECON_DB_PORT=5432
export H3XRECON_DB_PASS=h3xrecon
export H3XRECON_REDIS_HOST=$H3XRECON_PROCESSOR_HOST
export H3XRECON_REDIS_PORT=6379
export H3XRECON_NATS_HOST=$H3XRECON_PROCESSOR_HOST
export H3XRECON_NATS_PORT=4222
export H3XRECON_LOG_LEVEL=DEBUG
export H3XRECON_LOG_FILE_PATH=h3xrecon.log
# Set PYTHONPATH to src directory
export PYTHONPATH="$PWD/src"
# Set PostgreSQL environment for easy use of psql
export PGHOST=$H3XRECON_DB_HOST
export PGPORT=$H3XRECON_DB_PORT
export PGUSER=$H3XRECON_DB_USER
export PGPASSWORD=$H3XRECON_DB_PASS
export PGDATABASE=$H3XRECON_DB_NAME
# Set Ansible environment
export ANSIBLE_HOME=./src/ansible
export ANSIBLE_INVENTORY=./src/ansible/hosts.yaml
export ANSIBLE_LOCAL_TEMP=./.ansible_tmp


# Activate Python virtual environment
source ./venv/bin/activate

# Source h3xrecon completion
#. ./src/h3xrecon/cli/h3xrecon-complete.sh

# Ansible Playbook wrapper
apb() {
    alias ls=ls
    local playbook="$1"
    if [[ -z "$playbook" ]]; then
        # If no argument, list available playbooks
        echo "Available Ansible playbooks:"
        find ./src/ansible/ -maxdepth 1 -type f ! -name 'hosts.yaml' -name *.yaml  | xargs -n1 basename | cut -d. -f1
        return 1
    fi

    # Auto-complete .yaml extension if not provided
    if [[ ! "$playbook" == *.yaml ]]; then
        playbook="${playbook}.yaml"
    fi

    # Check if playbook exists
    if [[ ! -f "./src/ansible/$playbook" ]]; then
        echo "Playbook not found: $playbook"
        echo "Available Ansible playbooks:"
        ls ./src/ansible/*.yaml | xargs -n1 basename
        return 1
    fi

    ansible-playbook "./src/ansible/$playbook"
}

# Enable tab completion for Ansible playbooks
_apb_completion() {
    local cur playbooks
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    playbooks=$(ls ./src/ansible/*.yaml | xargs -n1 basename | sed 's/\.yaml$//')

    COMPREPLY=( $(compgen -W "${playbooks}" -- "${cur}") )
    return 0
}

complete -F _apb_completion apb