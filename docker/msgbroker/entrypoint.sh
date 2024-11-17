#!/bin/sh

# Start NATS server in the background
nats-server -js --store_dir=/data -m 8222 &

if [ -z $(which nats) ]; then
    echo "installing nats cli"
    wget https://github.com/nats-io/natscli/releases/download/v0.1.5/nats-0.1.5-linux-amd64.zip
    unzip nats-0.1.5-linux-amd64.zip
    mv nats-0.1.5-linux-amd64/nats /usr/local/bin/
    rm -rf nats-0.1.5-linux-amd64*
fi

# Run init script once
sh /init.sh

# Wait for NATS server to exit
wait