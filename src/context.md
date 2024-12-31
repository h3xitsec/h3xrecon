# H3xRecon Project Context

## Overview
H3xRecon is a bug bounty reconnaissance automation system that provides a customizable all-in-one automated reconnaissance infrastructure. It is designed to help security researchers and bug bounty hunters efficiently gather and process information about target systems.

## Architecture
1. Server Components
   - Parsing Worker: Processes function outputs and generates asset information
   - Data Worker: Handles data validation and storage, triggers new reconnaissance jobs
   - Recon Worker: Executes reconnaissance functions and tools

2. Core Components
   - Database Manager: Handles all database interactions
   - Queue Manager: Manages NATS message streams
   - Config Manager: Handles component configuration
   - Plugins: Modular functions for execution and output parsing

3. Client Components
   - API Interface: Handles client-server communication
   - Client Queue: Manages client-side NATS interactions
   - Client Database: Handles local data storage

## Message Flow
1. Client sends job requests to FUNCTION_EXECUTE stream
2. Recon Worker executes the function and sends output to FUNCTION_OUTPUT stream
3. Parsing Worker parses output and sends to RECON_DATA stream
4. Data Worker validates and stores data, triggers new jobs as needed

## Technical Stack
- Primary Language: Python
- Message Broker: NATS
- Cache Server: Redis (execution timestamps, recon worker status)
- Database: PostgreSQL with PGBouncer
- Deployment: Docker Swarm/Compose

## Development Guidelines
- Follow established database schema
- Maintain component consistency
- Write comprehensive tests
- Document new features and changes
- Follow secure coding practices

## Infrastructure
- Distributed architecture
- Scalable worker deployment
- Message-driven communication
- Containerized components

## Detailed component workflow and intended behavior

### Recon Worker

- Recon Worker receives a message from the FUNCTION_EXECUTE stream
- Recon Worker validates the message and executes the function
- Recon Worker sends the result to the FUNCTION_OUTPUT stream
- The Recon Worker should only run one function at a time
- The Recon Worker should not receive any other messages while processing a function
- The Recon Worker should not hold any messages while processing a function
- If a new message is sent to the queue while a recon worker is processing a function, it should be processed by another idle recon worker

## Future Scope
- Enhanced plugin system
- Advanced reporting capabilities
- Extended tool integration
- Performance optimizations
