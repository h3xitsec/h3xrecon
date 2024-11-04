#!/etc/profiles/per-user/h3x/bin/bash
trap 'echo Exited!; exit;' SIGINT SIGTERM
unset DOCKER_HOST
echo "===================================="
echo "         Building h3xrecon          "
echo "===================================="

echo "------------------------------------"
echo " Staging build directory            "
echo "------------------------------------"

sudo rm -rf build/*
mkdir -p ./build

cp -r src/BaseImage ./build/
cp -r src/Worker ./build/
cp -r src/DatabaseManager build/Worker/
cp -r src/QueueManager build/Worker/
cp src/requirements_workers.txt build/Worker/requirements.txt

cp -r src/DataProcessor ./build/
cp -r src/QueueManager build/DataProcessor/
cp src/requirements_processor.txt build/DataProcessor/requirements.txt

cp -r src/JobProcessor ./build/
cp -r src/QueueManager build/JobProcessor/
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
    echo "      Building docker images        "
    echo "===================================="
    
    echo "------------------------------------"
    echo " Building BaseImage                 "
    echo "------------------------------------"
    docker buildx build --push --file ./build/BaseImage/Dockerfile --platform linux/amd64,linux/arm64 --tag ghcr.io/h3xitsec/h3xrecon_base:latest ./build/BaseImage
    
    echo "------------------------------------"
    echo " Building Worker                    "
    echo "------------------------------------"
    docker buildx build --push --file ./build/Worker/Dockerfile --platform linux/amd64,linux/arm64 --tag ghcr.io/h3xitsec/h3xrecon_worker:latest ./build/Worker
    
    echo "------------------------------------"
    echo " Building DataProcessor             "
    echo "------------------------------------"
    docker buildx build --push --file ./build/DataProcessor/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_dataprocessor:latest ./build/DataProcessor
    
    echo "------------------------------------"
    echo " Building JobProcessor              "
    echo "------------------------------------"
    docker buildx build --push --file ./build/JobProcessor/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_jobprocessor:latest ./build/JobProcessor
    
    echo "------------------------------------"
    echo " Building Logger                    "
    echo "------------------------------------"
    docker buildx build --push --file ./build/Logger/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_logger:latest ./build/Logger
    
    echo "------------------------------------"
    echo " Building Nats                      "
    echo "------------------------------------"
    docker buildx build --push --file ./build/nats/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_nats:latest ./build/nats
    
    echo "------------------------------------"
    echo " Building Pgsql                     "
    echo "------------------------------------"
    docker buildx build --push --file ./build/pgsql/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_pgsql:latest ./build/pgsql

    echo "===================================="
    echo " Docker build commands completed!   "
    echo "===================================="
fi
