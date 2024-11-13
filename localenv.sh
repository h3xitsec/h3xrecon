#!/bin/bash

export H3XRECON_BASE_DIRECTORY=$(pwd)

# Source python virtual environment
if [[ $VIRTUAL_ENV ]]; then
    deactivate
fi

if [[ -f ${H3XRECON_BASE_DIRECTORY}/venv/bin/activate ]]; then
    source ${H3XRECON_BASE_DIRECTORY}/venv/bin/activate
else
    # Check if python3-venv is installed
    if ! dpkg -s python3-venv >/dev/null 2>&1; then
        echo "python3-venv is not installed. Installing..."
        sudo apt update && sudo apt install -y python3-venv
    fi
    python3 -m venv venv
    source ${H3XRECON_BASE_DIRECTORY}/venv/bin/activate
    pip install -r ${H3XRECON_BASE_DIRECTORY}/requirements.txt > /dev/null 2>&1
fi

# Environment variables
## reconh3x specific variables
set -a && . ./.env.local && set +a

# Add bin directory to PATH for local wrapper scripts
export PATH="$PWD/bin:$PATH"

# Set PostgreSQL environment for easy use of psql
export PGHOST=$H3XRECON_DB_HOST
export PGPORT=$H3XRECON_DB_PORT
export PGUSER=$H3XRECON_DB_USER
export PGPASSWORD=$H3XRECON_DB_PASS
export PGDATABASE=$H3XRECON_DB_NAME
# Set Ansible environment
export ANSIBLE_HOME=./ansible
export ANSIBLE_INVENTORY=./ansible/hosts.yaml
export ANSIBLE_LOCAL_TEMP=./.ansible_tmp

alias h3xrecon='docker run --rm -it --network host --env-file ${H3XRECON_BASE_DIRECTORY}/.env.local ghcr.io/h3xitsec/h3xrecon_client'