# Data Processor Component Documentation
## Overview
The Data Processor is a core component of the H3XRecon system responsible for processing and storing reconnaissance data. It handles different types of data (domains, IPs, URLs, services), validates them against program scope, and manages the triggering of follow-up reconnaissance jobs.
## Core Responsibilities
### 1. Data Processing
- Processes four main types of reconnaissance data:
- Domains
- IP addresses
- URLs
- Network services
- Validates data against program scope
- Stores processed data in the database
- Maintains data relationships and attributes
### 2. Job Chaining
- Automatically triggers follow-up reconnaissance jobs based on discovered data
- Uses predefined job mapping configuration:
- Domain discoveries trigger DNS and HTTP tests
- IP discoveries trigger reverse DNS and port scanning
- Controls job flow through environment variables
### 3. Scope Management
- Validates all data against program scope definitions
- Filters out-of-scope discoveries
- Ensures data compliance with program boundaries
## Architecture
### Data Flow
1. Receives data through the recon.data message stream
2. Identifies data type and routes to appropriate processor
3. Validates and stores data
4. Triggers relevant follow-up jobs
Reference:
```python:src/h3xrecon/server/dataprocessor.py
    JOB_MAPPING: Dict[str, List[JobConfig]] = {
        "domain": [
            JobConfig(function="test_domain_catchall", param_map=lambda result: {"target": result.lower()}),
            JobConfig(function="resolve_domain", param_map=lambda result: {"target": result.lower()}),
            JobConfig(function="test_http", param_map=lambda result: {"target": result.lower()})
        ],
        "ip": [
            JobConfig(function="reverse_resolve_ip", param_map=lambda result: {"target": result.lower()}),
            JobConfig(function="port_scan", param_map=lambda result: {"target": result.lower()})
        ]
    }
```
## Data Types and Processing
### 1. Domain Processing
- Validates domain against program scope
- Stores domain information including:
- Associated IP addresses
- CNAME records
- Catchall status
- Triggers DNS and HTTP testing jobs
### 2. IP Processing
- Stores IP addresses with PTR records
- Maintains program association
- Triggers reverse DNS and port scanning
### 3. URL Processing
- Extracts and validates hostname
- Stores HTTP response data
- Manages URL testing and validation
### 4. Service Processing
- Records network service information:
- IP address
- Port number
- Protocol
- Service identification
## Integration Points
### Message Queue
- Subscribes to recon.data stream
- Publishes new jobs to function.execute stream
- Handles message processing asynchronously
### Database
- Stores all processed reconnaissance data
- Maintains relationships between different data types
- Handles data deduplication
## Configuration
### Environment Variables
- H3XRECON_NO_NEW_JOBS: Controls automatic job triggering
- Configurable database and message queue settings
- Logging configuration options
## Deployment
The Data Processor runs as a single instance alongside other processor components. Example deployment configuration:
```yaml:docker_swarm/docker-compose.swarm.yaml
    dataprocessor:
      image: ghcr.io/h3xitsec/h3xrecon/server:latest
      depends_on:
        - msgbroker:service_healthy
        - cache:service_healthy
        - database:service_healthy
      environment:
        - H3XRECON_DB_USER
        - H3XRECON_DB_NAME
        - H3XRECON_DB_HOST
        - H3XRECON_DB_PASS
        - H3XRECON_REDIS_HOST
        - H3XRECON_REDIS_PORT
        - H3XRECON_NATS_HOST
        - H3XRECON_NATS_PORT
        - H3XRECON_LOG_LEVEL
        - H3XRECON_LOG_FILE_PATH
        - H3XRECON_ROLE=dataprocessor
      deploy:
        mode: replicated
        replicas: 1
        placement:
          constraints:
            - node.labels.H3XRECON_SWARM_ROLE == processor
```