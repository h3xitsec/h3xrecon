#!/usr/bin/env bash
trap 'echo Exited!; exit;' SIGINT SIGTERM
unset DOCKER_HOST
echo "===================================="
echo "         Building h3xrecon          "
echo "===================================="

echo "===================================="
echo "      Building docker images        "
echo "===================================="



cp setup.py ./src/docker/h3xrecon/
cp -r src/h3xrecon ./src/docker/h3xrecon/
cp .src/h3xrecon/psql_dump.sql ./src/docker/pgsql/

if [ -z "$GITHUB_ACTIONS" ]; then
echo "------------------------------------"
    echo " Building Reconh3x image            "
    echo "------------------------------------"

    docker buildx build --output type=docker --file ./src/docker/h3xrecon/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon:latest ./src/docker/h3xrecon/

    echo "------------------------------------"
    echo " Building Msg Broker                "
    echo "------------------------------------"

    docker buildx build --output type=docker --file ./src/docker/msgbroker/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_msgbroker:latest ./src/docker/msgbroker/

    echo "------------------------------------"
    echo " Building Pgsql                     "
    echo "------------------------------------"

    docker buildx build --output type=docker --file ./src/docker/pgsql/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_pgsql:latest ./src/docker/pgsql/

    echo "===================================="
    echo " Docker build commands completed!   "
    echo "===================================="

    rm -rf ./src/docker/h3xrecon/h3xrecon
    rm ./src/docker/h3xrecon/setup.py
fi
