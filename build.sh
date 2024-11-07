#!/etc/profiles/per-user/h3x/bin/bash
trap 'echo Exited!; exit;' SIGINT SIGTERM
unset DOCKER_HOST
echo "===================================="
echo "         Building h3xrecon          "
echo "===================================="

if [ -z "$GITHUB_ACTIONS" ]; then
    echo "===================================="
    echo "      Setup for local dev           "
    echo "===================================="

    cp src/docker-compose.local.yaml build/
    cp .env build/

    if [ "$1" != "--skip-build" ]; then
        echo "===================================="
        echo "      Building docker images        "
        echo "===================================="
        
        PUSH_FLAG=""
        if [ "$1" != "--skip-push" ]; then
            PUSH_FLAG="--push"
        else
            PUSH_FLAG="--output type=docker"
        fi
        
        echo "------------------------------------"
        echo " Building BaseImage                 "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./new_src/docker/base/Dockerfile.base --platform linux/amd64,linux/arm64 --tag ghcr.io/h3xitsec/h3xrecon-base:latest ./new_src
        
        echo "------------------------------------"
        echo " Building Worker                    "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./new_src/docker/worker/Dockerfile.worker --platform linux/amd64,linux/arm64 --tag ghcr.io/h3xitsec/h3xrecon-worker:latest ./new_src
        
        echo "------------------------------------"
        echo " Building DataProcessor             "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./new_src/docker/processor/Dockerfile.processor --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon-dataprocessor:latest ./new_src
        
        echo "------------------------------------"
        echo " Building JobProcessor              "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./new_src/docker/processor/Dockerfile.processor --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon-jobprocessor:latest ./new_src

        echo "------------------------------------"
        echo " Building Logger                    "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./new_src/docker/logger/Dockerfile.logger --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon-logger:latest ./new_src
        
        echo "------------------------------------"
        echo " Building Nats                      "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./new_src/docker/nats/Dockerfile.nats --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon-nats:latest ./new_src
        
        echo "------------------------------------"
        echo " Building Pgsql                     "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./new_src/docker/pgsql/Dockerfile.pgsql --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon-pgsql:latest ./new_src

        echo "===================================="
        echo " Docker build commands completed!   "
        echo "===================================="
    else
        echo "===================================="
        echo " Skipping docker image builds       "
        echo "===================================="
    fi
fi
