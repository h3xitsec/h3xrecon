# H3XRecon h3xrecon

<p align="center">
  <img src="assets/logo.png" alt="H3XRecon Logo" width="200"/>
</p>

H3XRecon client is a powerful command-line tool designed for managing and orchestrating reconnaissance data across multiple security programs. It provides a robust interface for managing programs, domains, IPs, URLs, and services with advanced filtering capabilities.

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Command Reference](#command-reference)
  - [System Management](#system-management)
  - [Program Management](#program-management)
  - [Scope Management](#scope-management)
  - [CIDR Management](#cidr-management)
  - [Job Management](#job-management)
  - [Asset Management](#asset-management)
- [Advanced Usage](#advanced-usage)
- [Configuration Examples](#configuration-examples)

## 🚀 Installation


### From source
```bash
# Clone the repository
git clone https://github.com/h3xitsec/h3xrecon-cli.git

# Navigate to the project directory
cd h3xrecon-cli

# Install the module
pip install .
```

### From Docker
```bash
# Pull the docker image
docker pull ghcr.io/h3xitsec/h3xrecon_client

# Setup an alias for running the client from docker
alias h3xrecon='docker run --rm -it --network host --env-file ${PWD}/.env.local ghcr.io/h3xitsec/h3xrecon_client'
```

## 🎯 Quick Start

```bash
# Create a new program
h3xrecon program add my-program

# Add scope to your program
h3xrecon -p my-program config add scope ".example.com"

# Add CIDR range
h3xrecon -p my-program config add cidr "192.168.1.0/24"

# Submit your first reconnaissance job
h3xrecon -p my-program sendjob resolve_domain example.com
```

## 📖 Command Reference

### System Management

Monitor and manage system queues:

```bash
# View queue status
h3xrecon system queue show <queue_name>

# List queue messages
h3xrecon system queue messages <queue_name>

# Clear queue
h3xrecon system queue flush <queue_name>
```

### Program Management

Programs are isolated environments for organizing reconnaissance data:

```bash
# List all programs
h3xrecon program list

# Create a new program
h3xrecon program add <program_name>

# Remove a program
h3xrecon program del <program_name>
```

### Scope Management

Control what's in scope for your reconnaissance:

```bash
# List current scope patterns
h3xrecon -p <program_name> config list scope

# Add scope pattern
h3xrecon -p <program_name> config add scope ".example.com"

# Bulk add scope patterns
cat scope.txt | h3xrecon -p <program_name> config add scope -

# Remove scope pattern
h3xrecon -p <program_name> config del scope ".example.com"
```

### CIDR Management

Manage IP ranges for your program:

```bash
# List configured CIDRs
h3xrecon -p <program_name> config list cidr

# Add CIDR range
h3xrecon -p <program_name> config add cidr "10.0.0.0/8"

# Bulk add CIDR ranges
cat cidrs.txt | h3xrecon -p <program_name> config add cidr -
```

### Job Management

Submit and manage reconnaissance jobs:

```bash
# Submit a new job
h3xrecon -p <program_name> sendjob <function_name> <target>

# Force job execution (bypass cache)
h3xrecon -p <program_name> sendjob <function_name> <target> --force
```

### Asset Management

#### Domains

```bash
# List all domains
h3xrecon -p <program_name> list domains

# List only resolved domains
h3xrecon -p <program_name> list domains --resolved

# Remove domain
h3xrecon -p <program_name> del domain example.com
```

#### IPs

```bash
# List all IPs
h3xrecon -p <program_name> list ips

# List IPs with PTR records
h3xrecon -p <program_name> list ips --resolved

# Remove IP
h3xrecon -p <program_name> del ip 1.1.1.1
```

#### URLs

```bash
# List all URLs
h3xrecon -p <program_name> list urls

# Remove URL
h3xrecon -p <program_name> del url https://example.com
```

## 🔧 Advanced Usage

### Bulk Operations

Most commands support bulk operations using stdin:

```bash
# Bulk add domains
cat domains.txt | h3xrecon -p <program_name> add domains -

# Bulk remove IPs
cat ips.txt | h3xrecon -p <program_name> del ip -
```

### Configuration Files

Example configuration files for bulk operations:

#### `scope.txt`
```text
.example.com
.test.example.com
```

#### `cidrs.txt`
```text
192.168.1.0/24
10.0.0.0/8
172.16.0.0/12
```

## 📝 Notes

- The `-p` or `--program` flag is required for most operations
- Use `-` to read input from stdin for bulk operations
- The `--resolved` and `--unresolved` flags are available for domains and IPs
- All operations provide feedback on success or failure
- Commands are case-sensitive