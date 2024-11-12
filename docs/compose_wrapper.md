# Compose Wrapper Usage Guide

The `compose.sh` script is a wrapper around `docker compose` that helps manage the Docker registry configuration and provides convenient defaults.

## Basic Usage

### First-time setup
```bash
# Set registry to local development
./compose.sh local

# Set registry to public (production)
./compose.sh public
```

### Common Operations
```bash
# Start the stack (uses last configured registry)
./compose.sh up -d

# View logs of all services
./compose.sh logs -f

# View logs of specific service
./compose.sh logs -f worker

# Execute command in a container
./compose.sh exec worker bash

# Check service status
./compose.sh ps

# Stop all services
./compose.sh down
```

## Registry Selection

The script handles the Docker registry in two ways:

1. **Explicit Registry Selection**:
   ```bash
   # Set to local registry and start services
   ./compose.sh local
   
   # Set to public registry and start services
   ./compose.sh public
   ```

2. **Use Last Selected Registry**:
   ```bash
   # Uses the registry setting from .current_registry file
   ./compose.sh ps
   ```

## Default Behavior

- When using `local` or `public` without additional arguments:
  ```bash
  ./compose.sh local
  # Will only set the registry
  ```

- When providing additional arguments:
  ```bash
  ./compose.sh local exec worker hostname
  # Equivalent to:
  # docker compose -f docker-compose.local.yaml exec worker hostname
  ```

## Tips

- The registry selection is stored in `.current_registry` file
- You only need to specify `local` or `public` when changing registry configuration
- All standard `docker compose` commands are supported