#!/etc/profiles/per-user/h3x/bin/bash

echo "Building h3xrecon"

sudo rm -rf build/*
mkdir -p ./build

cp -r src/BaseImage ./build/
cp -r src/Worker ./build/
cp -r src/DatabaseManager build/Worker/
cp -r src/QueueManager build/Worker/
cp src/requirements_workers.txt build/Worker/requirements.txt

#docker buildx build --file ./src/Worker/Dockerfile --platform linux/amd64 --tag ghcr.io/h3xitsec/h3xrecon_worker:latest ./src/Worker


#echo "Directory tree"
# find . | sed -e "s/[^-][^\/]*\//  |/g" -e "s/|\([^ ]\)/|-\1/"

# cp src/docker-compose_swarm.yaml build/docker-compose.yaml
# cp src/requirements_node.txt build/requirements.txt
# cp -r src/BaseImage build/BaseImage
# cp -r secrets build/
# echo "H3XRECON_PROCESSOR_IP=localhost" > build/.env
# cat .env >> build/.env


# echo "Building Processor Package"

# sudo rm -rf build/JobProcessor
# sudo rm -rf build/BaseImage
# sudo rm -rf build/DataProcessor
# sudo rm -rf build/Logger
# sudo rm -rf build/Nats
# sudo rm -rf build/Postgres

# mkdir build/BaseImage
# mkdir build/JobProcesor
# mkdir build/DataProcessor
# mkdir build/Logger
# mkdir build/nats
# mkdir build/pgsql

# mkdir build/DatabaseManager
# mkdir build/QueueManager

# ## Processor
# # Job Processor
# cp -r src/JobProcessor build/
# cp -r src/DatabaseManager build/JobProcessor/
# cp -r src/QueueManager build/JobProcessor/
# cp -r secrets build/JobProcessor
# cp src/requirements_processor.txt build/JobProcessor/requirements.txt

# cp -r src/Logger build/JobProcessor/
# cp -r src/pgsql build/Processor/
# cp -r src/nats build/Processor/
# cp -r src/DatabaseManager build/Processor/
# cp -r src/QueueManager build/Processor/
# cp -r src/BaseImage build/Processor/
# cp -r secrets build/Processor/
# cp -r src/tailscale build/Processor/
# cp src/docker-compose.processor.yaml build/Processor/docker-compose.yaml
# cp src/requirements_processor.txt build/Processor/requirements.txt
# echo "H3XRECON_PROCESSOR_IP=localhost" > build/Processor/.env
# cat .env >> build/Processor/.env

# mv build/Processor/JobProcessor/Dockerfile build/Processor/Dockerfile.job_processor
# mv build/Processor/DataProcessor/Dockerfile build/Processor/Dockerfile.data_processor
# mv build/Processor/Logger/Dockerfile build/Processor/Dockerfile.logger


# find ./build/Processor -type d -name __pycache__ | xargs -i{} sh -c "rm -rf {}"

# echo "Processor: Done"

# echo "Building Worker Package"

# sudo rm -rf build/Worker
# mkdir build/Worker

# ## Worker
# cp -r src/Worker build/Worker/
# mv build/Worker/Worker/Dockerfile build/Worker/Dockerfile
# cp -r src/DatabaseManager build/Worker/
# cp -r src/QueueManager build/Worker/
# cp -r src/BaseImage build/Worker/
# cp -r secrets build/Worker/
# cp -r src/tailscale build/Worker/
# cp src/docker-compose.workers.yaml build/Worker/docker-compose.yaml
# cp src/requirements_workers.txt build/Worker/requirements.txt
# echo "H3XRECON_PROCESSOR_IP=processor" > build/Worker/.env
# cat .env >> build/Worker/.env

# find ./build/Worker -type d -name __pycache__ | xargs -i{} sh -c "rm -rf {}"

# echo "Worker: Done"

# echo "Build Completed"