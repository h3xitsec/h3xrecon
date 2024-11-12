#!/usr/bin/env bash
trap 'echo Exited!; exit;' SIGINT SIGTERM
unset DOCKER_HOST
echo "======================================="
echo " Building H3xrecon DB and NATS images  "
echo "======================================="

docker buildx build --output type=docker --file ./docker/pgsql/Dockerfile --platform linux/amd64 --tag h3xrecontest/h3xrecon_pgsql:latest ./docker/pgsql/
docker buildx build --output type=docker --file ./docker/msgbroker/Dockerfile --platform linux/amd64 --tag h3xrecontest/h3xrecon_msgbroker:latest ./docker/msgbroker/

echo "======================================="
echo "    Docker image built successfully!   "
echo "======================================="