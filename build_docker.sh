#!/usr/bin/env bash

python -m hatchling build && \
docker build -t ghcr.io/h3xitsec/h3xrecon/database:dev -f ./Dockerfile.database . && \
docker build -t ghcr.io/h3xitsec/h3xrecon/server:dev -f ./Dockerfile.server . && \
docker build -t ghcr.io/h3xitsec/h3xrecon/worker:dev -f ./Dockerfile.worker . && \
docker build -t ghcr.io/h3xitsec/h3xrecon/client:dev -f ./Dockerfile.client . 
