#!/usr/bin/env bash

python -m hatchling build && \
docker build -t ghcr.io/h3xitsec/h3xrecon/server:dev -f ./Dockerfile.server .
