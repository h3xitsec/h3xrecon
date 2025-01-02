#!/bin/sh

# Wait for NATS to be ready
sleep 2

# Function to check if stream exists
stream_exists() {
    nats stream info "$1" --server=nats://localhost:4222 > /dev/null 2>&1
    return $?
}

for stream in RECON_INPUT WORKER_CONTROL WORKER_CONTROL_RESPONSE PARSING_INPUT DATA_INPUT LOGS_GENERAL; do
    if stream_exists "$stream"; then
        nats stream rm "$stream" --server=nats://localhost:4222 --force
    fi
done

if ! stream_exists "RECON_INPUT"; then
    nats stream add RECON_INPUT \
        --subjects "recon.input" \
        --retention limits \
        --max-age 24h \
        --storage file \
        --replicas 1 \
        --discard old \
        --max-msgs=-1 \
        --max-msgs-per-subject=-1 \
        --max-bytes=-1 \
        --max-msg-size=-1 \
        --dupe-window 2m \
        --no-allow-rollup \
        --no-deny-delete \
        --no-deny-purge \
        --server=nats://localhost:4222
    echo "Created RECON_INPUT stream"
else
    echo "RECON_INPUT stream already exists"
fi

if ! stream_exists "WORKER_CONTROL"; then
    nats stream add WORKER_CONTROL \
        --subjects "worker.control.>" \
        --retention interest \
        --max-age 1h \
        --storage file \
        --replicas 1 \
        --discard old \
        --max-msgs=-1 \
        --max-msgs-per-subject=-1 \
        --max-bytes=-1 \
        --max-msg-size=-1 \
        --dupe-window 1m \
        --no-allow-rollup \
        --no-deny-delete \
        --no-deny-purge \
        --server=nats://localhost:4222
    echo "Created WORKER_CONTROL stream"
fi

if ! stream_exists "WORKER_CONTROL_RESPONSE"; then
    nats stream add WORKER_CONTROL_RESPONSE \
        --subjects "worker.control.response" \
        --retention limits \
        --max-age 1h \
        --storage file \
        --replicas 1 \
        --discard old \
        --max-msgs=-1 \
        --max-msgs-per-subject=-1 \
        --max-bytes=-1 \
        --max-msg-size=-1 \
        --dupe-window 1m \
        --no-allow-rollup \
        --no-deny-delete \
        --no-deny-purge \
        --server=nats://localhost:4222
    echo "Created WORKER_CONTROL_RESPONSE stream"
else
    # Purge existing messages from the stream
    nats stream purge WORKER_CONTROL_RESPONSE --server=nats://localhost:4222 --force
    echo "Purged existing WORKER_CONTROL_RESPONSE stream"
fi

if ! stream_exists "PARSING_INPUT"; then
    nats stream add PARSING_INPUT \
        --subjects "parsing.input" \
        --retention limits \
        --max-age 24h \
        --storage file \
        --replicas 1 \
        --discard old \
        --max-msgs=-1 \
        --max-msgs-per-subject=-1 \
        --max-bytes=-1 \
        --max-msg-size=-1 \
        --dupe-window 2m \
        --no-allow-rollup \
        --no-deny-delete \
        --no-deny-purge \
        --server=nats://localhost:4222
    echo "Created PARSING_INPUT stream"
else
    # Optionally purge existing messages from the stream
    nats stream purge PARSING_INPUT --server=nats://localhost:4222 --force
    echo "Purged existing PARSING_INPUT stream"
fi

# # Create DATA_INPUT stream if it doesn't exist
# if ! stream_exists "DATA_INPUT"; then
#     nats stream add DATA_INPUT \
#         --subjects "data.input" \
#         --retention limits \
#         --max-age 24h \
#         --storage file \
#         --replicas 1 \
#         --discard old \
#         --max-msgs=-1 \
#         --max-msgs-per-subject=-1 \
#         --max-bytes=-1 \
#         --max-msg-size=-1 \
#         --dupe-window 2m \
#         --no-allow-rollup \
#         --no-deny-delete \
#         --no-deny-purge \
#         --server=nats://localhost:4222
#     echo "Created DATA_INPUT stream"
# else
#     echo "DATA_INPUT stream already exists"
# fi

if ! stream_exists "DATA_INPUT"; then
    nats stream add DATA_INPUT \
        --subjects "data.input" \
        --retention limits \
        --max-age 24h \
        --storage file \
        --replicas 1 \
        --discard old \
        --max-msgs=-1 \
        --max-msgs-per-subject=-1 \
        --max-bytes=-1 \
        --max-msg-size=-1 \
        --dupe-window 2m \
        --no-allow-rollup \
        --no-deny-delete \
        --no-deny-purge \
        --server=nats://localhost:4222
    echo "Created DATA_INPUT stream"
else
    echo "DATA_INPUT stream already exists"
fi