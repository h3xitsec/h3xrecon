#!/usr/bin/env bash

set -a && . ./.env.compose && set +a

show_menu() {
    echo "Please select a registry option:"
    echo "1) local  - Use local Docker registry (for development)"
    echo "2) public - Use public Docker registry (for production)"
    read -p "Enter your choice (1 or 2): " choice

    case $choice in
        1)
            H3XRECON_DOCKER_REGISTRY="h3xrecontest"
            ;;
        2)
            H3XRECON_DOCKER_REGISTRY="ghcr.io/h3xitsec"
            ;;
        *)
            echo "Invalid choice. Exiting."
            exit 1
            ;;
    esac
}

# Check if any arguments are provided
if [ $# -ge 1 ]; then
    case $1 in
        local|public)
            if [ $1 == "local" ]; then
                H3XRECON_DOCKER_REGISTRY="h3xrecontest"
            else
                H3XRECON_DOCKER_REGISTRY="ghcr.io/h3xitsec"
            fi
            export H3XRECON_DOCKER_REGISTRY
            echo $H3XRECON_DOCKER_REGISTRY > .current_registry
            echo "Registry set to: $H3XRECON_DOCKER_REGISTRY"
            
            shift
            if [ $# -ne 0 ]; then
                docker compose -f docker-compose.local.yaml $@
            fi
            ;;
        *)
            H3XRECON_DOCKER_REGISTRY=$(cat .current_registry)
            export H3XRECON_DOCKER_REGISTRY
            # If first arg is not local/public, pass all args to docker compose
            docker compose -f docker-compose.local.yaml $@
            ;;
    esac
else
    H3XRECON_DOCKER_REGISTRY=$(cat .current_registry)
    export H3XRECON_DOCKER_REGISTRY
    echo "Registry set to: $H3XRECON_DOCKER_REGISTRY"
    docker compose -f docker-compose.local.yaml up -d && docker compose -f docker-compose.local.yaml logs -f
fi