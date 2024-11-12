#!/bin/sh

# Start NATS server in the background
nats-server -js --store_dir=/data -m 8222 &

# Wait for NATS to be ready
sleep 2

# Run init script once
/init.sh

# Wait for NATS server to exit
wait