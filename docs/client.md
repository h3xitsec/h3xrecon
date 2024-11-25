# H3xRecon Client

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

### With Docker

```bash
# Pull the image
docker pull ghcr.io/h3xitsec/h3xrecon_cli:v0.0.3

# Create the configuration file
cat << EOF > ~/.h3xrecon/config.yaml
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "h3xrecon",
    "user": "h3xrecon",
    "password": "h3xrecon"
  },
  "nats": {
    "host": "localhost",
    "port": 4222
  },
  "logging": {
    "level": "DEBUG",
    "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> - <level>{message}</level>"
  }
}
EOF

# Create a shell alias for the h3xrecon command
alias h3xrecon="docker run --network=host --rm -it -v ~/.h3xrecon:/root/.h3xrecon ghcr.io/h3xitsec/h3xrecon_cli:v0.0.3"
```

## 🎯 Quick Start

```bash
Usage:
    h3xrecon ( program ) ( list )
    h3xrecon ( program ) ( add | del) ( <program> )
    h3xrecon ( program ) ( import ) ( <file> )
    h3xrecon [ -p <program> ] ( config ) ( add | del ) ( cidr | scope ) ( - | <item> )
    h3xrecon [ -p <program> ] ( config ) ( list ) ( cidr | scope )
    h3xrecon [ -p <program> ] ( config ) ( database ) ( drop)
    h3xrecon ( system ) ( queue ) ( show | messages | flush ) ( worker | job | data )
    h3xrecon [ -p <program> ] ( list ) ( domains | ips ) [--resolved] [--unresolved]
    h3xrecon [ -p <program> ] ( list ) ( urls | services ) [--details]
    h3xrecon [ -p <program> ] ( add | del ) ( domain | ip | url ) ( - | <item> )
    h3xrecon [ -p <program> ] ( sendjob ) ( <function> ) ( <target> ) [--force]
```

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

# Import programs from a yaml file
h3xrecon program import <file>
```

You can use the import command to quickly add multiple programs to your database and maintain them in a single file. 

Just update the file and run the command again to add new programs and/or new scopes and CIDRs.

For the program import command, the file should be a valid yaml file with the following structure:

```yaml
---
programs:
  - name: my_program
    scope:
      - myprogram\.com
      - .*app\.my_program\.com
      - .*api\.my_program\.com
    cidr:
      - 1.2.3.0/24
      - 1.2.4.0/24
  - name: my_other_program
    scope:
      - myotherprogram\.com
      - .*app\.my_other_program\.com
      - .*api\.my_other_program\.com
    cidr:
      - 4.5.6.0/24
      - 3.4.0.0/16
```


#### Scope Management

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

#### CIDR Management

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

#### Recon Plugins

The sendjob command is used to submit reconnaissance jobs to the system. 

The following reconnaissance functions are available:

##### expand_cidr

Expand a CIDR range into a list of IPs and dispatch them to the reverse_resolve_ip function.

```bash
h3xrecon -p <program_name> sendjob expand_cidr "192.168.1.0/24"
```

Tools used:
- [prips](https://gitlab.com/prips/prips)

##### resolve_domain

Resolve a domain to its IP addresses and CNAME records.

```bash
h3xrecon -p <program_name> sendjob resolve_domain example.com
```

Tools used:
- [dnsx](https://github.com/projectdiscovery/dnsx)

##### reverse_resolve_ip

Resolve an IP address to its PTR record

```bash
h3xrecon -p <program_name> sendjob reverse_resolve_ip 1.1.1.1
```

Tools used:
- [dnsx](https://github.com/projectdiscovery/dnsx)

##### test_http

Test if a domain is reachable over HTTP(S) on multiples ports : 80-99,443-449,11443,8443-8449,9000-9003,8080-8089,8801-8810,3000,5000

```bash
h3xrecon -p <program_name> sendjob test_http example.com
```

Tools used:
- [httpx](https://github.com/projectdiscovery/httpx)

##### find_subdomains

This plugin is a meta-plugin that will dispatch subdomain discovery jobs to the following plugins:

- find_subdomains_ctfr
- find_subdomains_subfinder

##### find_subdomains_ctfr

Uses CTFR to find subdomains from the Certificate Transparency logs.

Tools used:
- [ctfr](https://github.com/UnaPibaGeek/ctfr)

##### find_subdomains_subfinder

Uses Subfinder to find subdomains.

Tools used:
- [subfinder](https://github.com/projectdiscovery/subfinder)

##### port_scan

Scans an IP address for the top 1000 ports.

```bash
h3xrecon -p <program_name> sendjob port_scan 1.1.1.1
```

Tools used:
- [nmap](https://github.com/nmap/nmap)

##### test_domain_catchall

Test if a domain is a catch-all domain.

```bash
h3xrecon -p <program_name> sendjob test_domain_catchall example.com
```

Tools used:
- [dns.resolver](https://docs.python.org/3/library/dns.resolver.html)

##### subdomain_permutation

Generate a permutation list of subdomains from a given domain and dispatch them to the resolve_domain function.

This plugin will skip domains that are known to be catch-all domains and will instead dispatch them to the test_domain_catchall function if the catch-all status is unknown.

```bash
h3xrecon -p <program_name> sendjob subdomain_permutation example.com
```

Tools used:
- [gotator](https://github.com/Josue87/gotator)

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