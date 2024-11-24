#!/usr/bin/env bash

docker build -t ghcr.io/h3xitsec/h3xrecon_database:dev -f ./Dockerfile.database . && \
docker build -t ghcr.io/h3xitsec/h3xrecon_server:dev -f ./Dockerfile.server . && \
docker build -t ghcr.io/h3xitsec/h3xrecon_worker:dev -f ./Dockerfile.worker .
