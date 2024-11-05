#!/etc/profiles/per-user/h3x/bin/bash
trap 'echo Exited!; exit;' SIGINT SIGTERM
unset DOCKER_HOST
echo "===================================="
echo "         Building h3xrecon          "
echo "===================================="

echo "------------------------------------"
echo " Staging build directory            "
echo "------------------------------------"

rm -rf build/*
mkdir -p ./build

cp src/docker-compose.yaml ./build/

cp -r src/Client ./build/
cp -r src/DatabaseManager build/Client/
cp -r src/QueueManager build/Client/
cp src/requirements_client.txt build/Client/requirements.txt

cp -r src/BaseImage ./build/
cp -r src/Worker ./build/
cp -r src/DatabaseManager build/Worker/
cp -r src/QueueManager build/Worker/
cp src/requirements_workers.txt build/Worker/requirements.txt

cp -r src/DataProcessor ./build/
cp -r src/QueueManager build/DataProcessor/
cp -r src/DatabaseManager build/DataProcessor/
cp src/requirements_processor.txt build/DataProcessor/requirements.txt

cp -r src/JobProcessor ./build/
cp -r src/QueueManager build/JobProcessor/
cp -r src/DatabaseManager build/JobProcessor/
cp src/requirements_processor.txt build/JobProcessor/requirements.txt

cp -r src/Logger ./build/
cp -r src/DatabaseManager build/Logger/
cp -r src/QueueManager build/Logger/
cp src/requirements_processor.txt build/Logger/requirements.txt

cp -r src/nats build/nats
cp -r src/pgsql build/pgsql

echo "------------------------------------"
echo " Staging build directory completed  "
echo "------------------------------------"

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
        docker buildx build $PUSH_FLAG --file ./build/BaseImage/Dockerfile --platform linux/amd64,linux/arm64 --tag ghcr.io/h3xitsec/h3xrecon_base:latest ./build/BaseImage
        
        echo "------------------------------------"
        echo " Building Worker                    "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./build/Worker/Dockerfile --platform linux/amd64,linux/arm64 --tag ghcr.io/h3xitsec/h3xrecon_worker:latest ./build/Worker
        
        echo "------------------------------------"
        echo " Building DataProcessor             "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./build/DataProcessor/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_dataprocessor:latest ./build/DataProcessor
        
        echo "------------------------------------"
        echo " Building JobProcessor              "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./build/JobProcessor/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_jobprocessor:latest ./build/JobProcessor
        
        echo "------------------------------------"
        echo " Building Logger                    "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./build/Logger/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_logger:latest ./build/Logger
        
        echo "------------------------------------"
        echo " Building Nats                      "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./build/nats/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_nats:latest ./build/nats
        
        echo "------------------------------------"
        echo " Building Pgsql                     "
        echo "------------------------------------"
        docker buildx build $PUSH_FLAG --file ./build/pgsql/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_pgsql:latest ./build/pgsql

        echo "===================================="
        echo " Docker build commands completed!   "
        echo "===================================="
    else
        echo "===================================="
        echo " Skipping docker image builds       "
        echo "===================================="
    fi
fi
