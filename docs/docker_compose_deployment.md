# 🐳 Docker Compose Deployment

This guide explains how to deploy H3XRecon using Docker Compose for single-node setups.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`)
- Git
- 8GB RAM minimum
- 4 vCPUs minimum

## Deployment Steps

### 1. Clone the Repository

```bash
git clone https://github.com/h3xitsec/h3xrecon.git
cd h3xrecon
```

### 2. Configure Environment

Copy the example environment file and adjust settings as needed:

```bash
cp .env.compose.example .env.compose
```

Key settings to review:
- `H3XRECON_WORKERS_COUNT`: Number of worker containers (default: 1)
- `MONGODB_USERNAME`: Database username
- `MONGODB_PASSWORD`: Database password
- `REDIS_PASSWORD`: Cache password

### 3. Start the Stack

```bash
# Start all services
docker compose up -d

# View logs in real-time
docker compose logs -f
```

The following services will be deployed:
- MongoDB (database)
- Redis (cache)
- NATS (message broker)
- Grafana (monitoring)
- Loki (log aggregation)
- Promtail (log shipping)
- JobProcessor
- DataProcessor
- Worker(s)

### 4. Scale Workers

You can scale workers in two ways:

#### A. Dynamic Scaling

```bash
# Scale to desired number of workers
docker compose scale worker=<number_of_workers>
```

#### B. Environment Variable

```bash
# Set the environment variable
export H3XRECON_WORKERS_COUNT=5

# Reload the stack
docker compose up -d
```

Example output when scaling to 5 workers:
```
[+] Running 13/13
 ✔ Container h3xrecon-promtail-1       Running                                                                         0.0s 
 ✔ Container h3xrecon-loki-1           Running                                                                         0.0s 
 ✔ Container h3xrecon-database-1       Running                                                                         0.0s 
 ✔ Container h3xrecon-grafana-1        Running                                                                         0.0s 
 ✔ Container h3xrecon-msgbroker-1      Healthy                                                                         0.6s 
 ✔ Container h3xrecon-cache-1          Healthy                                                                         0.6s 
 ✔ Container h3xrecon-worker-1         Running                                                                         0.0s 
 ✔ Container h3xrecon-jobprocessor-1   Running                                                                         0.0s 
 ✔ Container h3xrecon-worker-3         Started                                                                         1.2s 
 ✔ Container h3xrecon-worker-4         Started                                                                         0.9s 
 ✔ Container h3xrecon-worker-5         Started                                                                         1.1s 
 ✔ Container h3xrecon-worker-2         Started                                                                         1.4s 
 ✔ Container h3xrecon-dataprocessor-1  Running                                                                         0.0s 
```

### 5. Access Services

- **Grafana**: http://localhost:3000
  - Default credentials: admin/admin
  - Pre-configured dashboards for monitoring

- **API**: http://localhost:8000
  - Documentation: http://localhost:8000/docs
  - Swagger UI: http://localhost:8000/swagger

## Maintenance

### View Service Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f worker
```

### Update Stack

```bash
# Pull latest images
docker compose pull

# Restart with new images
docker compose up -d
```

### Stop Stack

```bash
# Stop all services
docker compose down

# Stop and remove volumes (WARNING: Deletes all data)
docker compose down -v
```

## Troubleshooting

1. **Services not starting**: Check logs with `docker compose logs`
2. **Worker scaling issues**: Ensure enough system resources
3. **Database connection errors**: Verify MongoDB credentials in `.env.compose`

For more information on Docker Compose commands, please refer to the [Docker Compose Documentation](https://docs.docker.com/compose/).