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
# Set Docker Compose environment
export COMPOSE_FILE=./src/docker/docker-compose.local.yaml
export COMPOSE_ENV_FILES=./src/docker/.env.compose
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

# Ansible Playbook wrapper
apb() {
    ansible-playbook ./src/ansible/"$1"
}
