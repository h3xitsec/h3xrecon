# H3XRecon Client

<p align="center">
  <img src="assets/logo.png" alt="H3XRecon Logo" width="200"/>
</p>

H3XRecon Client is a powerful command-line tool designed for managing and orchestrating reconnaissance data across multiple security programs. It provides a robust interface for managing programs, domains, IPs, URLs, and services with advanced filtering capabilities.

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

```bash
# Clone the repository
git clone https://github.com/yourusername/h3xrecon.git

# Navigate to the project directory
cd h3xrecon

# Install dependencies
pip install -r requirements.txt
```

## 🎯 Quick Start

```bash
# Create a new program
client program add my-program

# Add scope to your program
client -p my-program config add scope ".example.com"

# Add CIDR range
client -p my-program config add cidr "192.168.1.0/24"

# Submit your first reconnaissance job
client -p my-program sendjob resolve_domain example.com
```

## 📖 Command Reference

### System Management

Monitor and manage system queues:

```bash
# View queue status
client system queue show <queue_name>

# List queue messages
client system queue messages <queue_name>

# Clear queue
client system queue flush <queue_name>
```

### Program Management

Programs are isolated environments for organizing reconnaissance data:

```bash
# List all programs
client program list

# Create a new program
client program add <program_name>

# Remove a program
client program del <program_name>
```

### Scope Management

Control what's in scope for your reconnaissance:

```bash
# List current scope patterns
client -p <program_name> config list scope

# Add scope pattern
client -p <program_name> config add scope ".example.com"

# Bulk add scope patterns
cat scope.txt | client -p <program_name> config add scope -

# Remove scope pattern
client -p <program_name> config del scope ".example.com"
```

### CIDR Management

Manage IP ranges for your program:

```bash
# List configured CIDRs
client -p <program_name> config list cidr

# Add CIDR range
client -p <program_name> config add cidr "10.0.0.0/8"

# Bulk add CIDR ranges
cat cidrs.txt | client -p <program_name> config add cidr -
```

### Job Management

Submit and manage reconnaissance jobs:

```bash
# Submit a new job
client -p <program_name> sendjob <function_name> <target>

# Force job execution (bypass cache)
client -p <program_name> sendjob <function_name> <target> --force
```

### Asset Management

#### Domains

```bash
# List all domains
client -p <program_name> list domains

# List only resolved domains
client -p <program_name> list domains --resolved

# Remove domain
client -p <program_name> del domain example.com
```

#### IPs

```bash
# List all IPs
client -p <program_name> list ips

# List IPs with PTR records
client -p <program_name> list ips --resolved

# Remove IP
client -p <program_name> del ip 1.1.1.1
```

#### URLs

```bash
# List all URLs
client -p <program_name> list urls

# Remove URL
client -p <program_name> del url https://example.com
```

## 🔧 Advanced Usage

### Bulk Operations

Most commands support bulk operations using stdin:

```bash
# Bulk add domains
cat domains.txt | client -p <program_name> add domains -

# Bulk remove IPs
cat ips.txt | client -p <program_name> del ip -
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

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.