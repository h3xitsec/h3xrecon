# Job Processor Component Documentation
## Overview
The Job Processor is a critical component in the H3XRecon system that handles the processing and management of reconnaissance function outputs. It acts as a bridge between the workers executing reconnaissance tasks and the data storage layer.
## Core Responsibilities
### 1. Output Processing
- Receives and processes output from reconnaissance functions
- Validates and transforms function results
- Ensures data is properly formatted before storage
- Manages scope validation for reconnaissance targets
### 2. Plugin Management
- Dynamically loads and manages output processing plugins
- Maintains a mapping of function names to their respective output processors
- Validates plugin compatibility and requirements
### 3. Execution Logging
- Tracks function executions and their results
- Maintains execution history in both database and Redis
- Provides execution timestamps for deduplication
## Architecture
### Message Flow
1. Workers execute reconnaissance functions and publish results to function.output
2. Job Processor subscribes to the output stream
3. Results are processed through appropriate plugins
4. Processed data is stored and logged
Reference:
python:src/h3xrecon/server/jobprocessor.py async def start(self): logger.info(f"Starting Job Processor (ID: {self.worker_id})...") await self.qm.connect() await self.qm.subscribe( subject="function.output", stream="FUNCTION_OUTPUT", durable_name="MY_CONSUMER", message_handler=self.message_handler, batch_size=1 )
### Plugin System
The Job Processor uses a dynamic plugin system that:
- Automatically discovers output processing plugins
- Loads plugins at runtime
- Maps function names to their processing methods
- Handles plugin errors gracefully
## Key Features
### 1. Execution Tracking
- Maintains detailed logs of function executions
- Stores execution metadata including:
- Execution ID
- Timestamp
- Function name
- Target
- Program ID
- Results
### 2. Scope Validation
- Validates targets against program scope
- Ensures reconnaissance data stays within defined boundaries
- Marks out-of-scope results appropriately
### 3. Error Handling
- Comprehensive error catching and logging
- Graceful handling of plugin failures
- Detailed error reporting with file and line information
## Integration Points
### Message Queue
- Subscribes to the function.output stream
- Processes messages in real-time
- Handles message batching and queueing
### Storage
- Interfaces with Redis for execution caching
- Writes to database through DatabaseManager
- Maintains execution history
## Deployment
The Job Processor is designed to run as a single instance per deployment, typically alongside other processor components. In a Docker Swarm setup, it's deployed with the processor role:
Reference:
```yaml:docker_swarm/docker-compose.swarm.yaml
    jobprocessor:
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
        - H3XRECON_ROLE=jobprocessor
      deploy:
        mode: replicated
        replicas: 1
        placement:
          constraints:
            - node.labels.H3XRECON_SWARM_ROLE == processor
```
## Monitoring
The component provides detailed logging that can be monitored through the Grafana dashboard. This logging helps track:
- Function execution status
- Processing errors
- Plugin loading issues
- Performance metrics