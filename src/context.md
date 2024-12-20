# H3xRecon Project Context

## Overview
H3xRecon is a bug bounty reconnaissance automation system that provides a customizable all-in-one automated reconnaissance infrastructure. It is designed to help security researchers and bug bounty hunters efficiently gather and process information about target systems.

## Architecture
1. Server Components
   - Job Processor: Processes function outputs and generates asset information
   - Data Processor: Handles data validation and storage, triggers new reconnaissance jobs
   - Worker: Executes reconnaissance functions and tools

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
2. Worker executes the function and sends output to FUNCTION_OUTPUT stream
3. Job Processor parses output and sends to RECON_DATA stream
4. Data Processor validates and stores data, triggers new jobs as needed

## Technical Stack
- Primary Language: Python
- Message Broker: NATS
- Cache Server: Redis (execution timestamps, worker status)
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

## Future Scope
- Enhanced plugin system
- Advanced reporting capabilities
- Extended tool integration
- Performance optimizations
