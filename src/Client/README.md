# H3XRecon Client Guide

## Notes

```bash
# Program creation and removal  
client program add <program_name>
client program del <program_name>
# Program configuration
client <-p program_name> config list scope
client <-p program_name> config list cidr
client <-p program_name> config add cidr <cidr>
client <-p program_name> config add scope <scope_pattern>
client <-p program_name> config del scope <scope_pattern>
# Job submission
client <-p program_name> sendjob <function_name> <target>
# Data Management
client <-p program_name> list domains
client <-p program_name> list ips
client <-p program_name> list urls
client <-p program_name> list services
client <-p program_name> del domain <domain>
client <-p program_name> del ip <ip>
client <-p program_name> del url <url>

```

## Overview
H3XRecon client is a command-line tool for managing reconnaissance data across different programs. It allows you to manage programs, domains, IPs, URLs, and services.

## Installation

```bash
git clone https://github.com/yourusername/h3xrecon.git
cd h3xrecon
pip install -r requirements.txt
```

## Program Management

### List Programs

```bash
client.py list program
```
### Add Program
```bash
client.py add program <program_name>
``` 

### Remove Program

```bash
client.py remove program <program_name>
```

### Scope Management

Scope is used to filter the data that is being processed. It is used to filter the data that is being processed by the program.
It is in the form of a regex pattern.

#### List Scope

```bash
client.py -p h3xit list scope
```

#### Add Scope

```bash
# Add a single scope pattern
client.py -p h3xit add scope ".h3xit.io"
# Add multiple scope patterns from stdin
cat scope.txt | client.py -p h3xit add scope -
```
#### Remove Scope

```bash
# Remove a single scope pattern
client.py -p h3xit remove scope ".h3xit.io"
# Remove multiple scope patterns from stdin
cat scope.txt | client.py -p h3xit remove scope -
```

## CIDR Management

#### List CIDR

```bash
client.py -p h3xit list cidr
```

#### Add CIDR

```bash
# Add a single CIDR
client.py -p h3xit add cidr "1.1.1.0/24"
# Add multiple CIDRs from stdin
cat cidrs.txt | client.py -p h3xit add cidr -
```

#### Remove CIDR

```bash
# Remove a single CIDR
client.py -p h3xit remove cidr "1.1.1.0/24"
# Remove multiple CIDRs from stdin
cat cidrs.txt | client.py -p h3xit remove cidr -
```

## Job Management

### Send Job

```bash
# Send a job to process a target
client.py -p h3xit sendjob resolve_domain example.h3xit.io
# Force job execution
client.py -p h3xit sendjob resolve_domain example.h3xit.io --force
```

## Domain Management

### List Domains

```bash
# List all domains for a program
client.py -p h3xit list domains
# List only resolved domains (domains with IP addresses)
client.py -p h3xit list domains --resolved
# List only unresolved domains (domains without IP addresses)
client.py -p h3xit list domains --unresolved
```

### Remove Domains

```bash
# Remove a single domain
client.py -p h3xit remove domain test.h3xit.io
# Remove multiple domains from stdin
cat domains.txt | client.py -p h3xit remove domain -
```

## IP Management

### List IPs

```bash
# List all IPs for a program
client.py -p h3xit list ips
# List only IPs with PTR records
client.py -p h3xit list ips --resolved
# List only IPs without PTR records
client.py -p h3xit list ips --unresolved
```

### Remove IPs

```bash
# Remove a single IP
client.py -p h3xit remove ip 1.1.1.1
# Remove multiple IPs from stdin
cat ips.txt | client.py -p h3xit remove ip -
```

## URL Management
### List URLs

```bash
# List all URLs for a program
client.py -p h3xit list urls
``` 

### Remove URLs

```bash
# Remove a single URL
client.py -p h3xit remove url http://test.h3xit.io
# Remove multiple URLs from stdin
cat urls.txt | client.py -p h3xit remove url -
```

## Service Management

### List Services

```bash
# List all services for a program
client.py -p h3xit list services
```

## Input File Examples

### domains.txt

```text
example.h3xit.io
test.h3xit.io
```

### ips.txt

```text
1.1.1.1
1.1.1.2
```

### urls.txt

```text
http://example.h3xit.io
https://test.h3xit.io
```

### cidrs.txt

```text
192.168.1.0/24
10.0.0.0/8
172.16.0.0/12
``` 

### scope.txt

```text
.h3xit.io
.test.h3xit.io
```


## Notes
- The `-p` or `--program` flag is required for most operations
- Use `-` to read input from stdin for bulk operations
- The `--resolved` and `--unresolved` flags are only available for domains and IPs
- All operations that modify data will provide feedback on success or failure