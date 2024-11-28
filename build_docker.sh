#!/usr/bin/env bash

./build_database_docker.sh && \
./build_server_docker.sh && \
./build_worker_docker.sh
