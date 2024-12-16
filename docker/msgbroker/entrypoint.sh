#!/bin/sh

# Start NATS server in the background
nats-server -js --store_dir=/data -m 8222 &

if [ -z $(which nats) ]; then
    echo "installing nats cli"
    attempts=0
    max_attempts=3
    success=false

    while [ $attempts -lt $max_attempts ] && [ "$success" = false ]; do
        if wget https://github.com/nats-io/natscli/releases/download/v0.1.5/nats-0.1.5-linux-amd64.zip && \
           unzip nats-0.1.5-linux-amd64.zip && \
           mv nats-0.1.5-linux-amd64/nats /usr/local/bin/ && \
           rm -rf nats-0.1.5-linux-amd64*; then
            success=true
        else
            attempts=$((attempts + 1))
            if [ $attempts -lt $max_attempts ]; then
                echo "Attempt $attempts failed. Retrying in 10 seconds..."
                sleep 10
            else
                echo "Failed to install nats cli after $max_attempts attempts"
                exit 1
            fi
        fi
    done
fi

# Run init script once
sh /init.sh

# Wait for NATS server to exit
wait