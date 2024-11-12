#!/bin/bash

# Environment variables
## reconh3x specific variables
set -a && . ./.env.local && set +a 
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

alias h3xrecon='docker run --rm -it --network host --env-file ./.env.local ghcr.io/h3xitsec/h3xrecon_client'

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