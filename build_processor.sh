#!/etc/profiles/per-user/h3x/bin/bash

echo "Building Processor Package"

sudo rm -rf build/Processor
mkdir build/Processor

## Processor
cp -r src/DataProcessor build/Processor/
cp -r src/JobProcessor build/Processor/
cp -r src/Logger build/Processor/
cp -r src/pgsql build/Processor/
cp -r src/nats build/Processor/
cp -r src/DatabaseManager build/Processor/
cp -r src/QueueManager build/Processor/
cp -r src/BaseImage build/Processor/
cp -r secrets build/Processor/
cp -r src/tailscale build/Processor/
cp src/docker-compose.processor.yaml build/Processor/docker-compose.yaml
cp src/requirements_processor.txt build/Processor/requirements.txt
echo "H3XRECON_PROCESSOR_IP=localhost" > build/Processor/.env
cat .env >> build/Processor/.env

mv build/Processor/JobProcessor/Dockerfile build/Processor/Dockerfile.job_processor
mv build/Processor/DataProcessor/Dockerfile build/Processor/Dockerfile.data_processor
mv build/Processor/Logger/Dockerfile build/Processor/Dockerfile.logger


find ./build/Processor -type d -name __pycache__ | xargs -i{} sh -c "rm -rf {}"

echo "Processor: Done"