# Docker Compose Deployment

## 1. Clone the repository:

```bash
git clone https://github.com/h3xitsec/h3xrecon.git
cd h3xrecon
```

## 2. Start the compose stack

```bash
docker compose up -d
docker compose logs -f
```

## 3. Scaling the workers

Hot scaling the workers is as simple as running the following command:

```bash
dockercompose scale worker=<number_of_workers>
```

Alternatively, you can set the number of workers in the .env.compose file and restart the compose stack.

```bash
# Set the environment variable
export H3XRECON_WORKERS_COUNT=5

# Reload the stack
docker compose up -d

# 4 new worker containers are spawned
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

## More informations

For more information on docker compose commands, please refer to the [Docker Compose Documentation](https://docs.docker.com/compose/).