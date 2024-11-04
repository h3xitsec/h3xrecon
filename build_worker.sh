#!/etc/profiles/per-user/h3x/bin/bash

echo "Building Worker Package"

sudo rm -rf build/Worker
mkdir build/Worker

## Worker
cp -r src/Worker build/Worker/
mv build/Worker/Worker/Dockerfile build/Worker/Dockerfile
cp -r src/DatabaseManager build/Worker/
cp -r src/QueueManager build/Worker/
cp -r src/BaseImage build/Worker/
cp -r secrets build/Worker/
cp -r src/tailscale build/Worker/
cp src/docker-compose.workers.yaml build/Worker/docker-compose.yaml
cp src/requirements_workers.txt build/Worker/requirements.txt
echo "H3XRECON_PROCESSOR_IP=processor" > build/Worker/.env
cat .env >> build/Worker/.env

find ./build/Worker -type d -name __pycache__ | xargs -i{} sh -c "rm -rf {}"

echo "Worker: Done"