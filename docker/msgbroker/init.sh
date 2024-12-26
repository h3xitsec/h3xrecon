#!/bin/sh

# Wait for NATS to be ready
sleep 2

# Function to check if stream exists
stream_exists() {
    nats stream info "$1" --server=nats://localhost:4222 > /dev/null 2>&1
    return $?
}

for stream in FUNCTION_EXECUTE FUNCTION_CONTROL FUNCTION_CONTROL_RESPONSE FUNCTION_OUTPUT RECON_DATA LOGS_GENERAL; do
    if stream_exists "$stream"; then
        nats stream rm "$stream" --server=nats://localhost:4222 --force
    fi
done

if ! stream_exists "FUNCTION_EXECUTE"; then
    nats stream add FUNCTION_EXECUTE \
        --subjects "function.execute" \
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
    echo "Created FUNCTION_EXECUTE stream"
else
    echo "FUNCTION_EXECUTE stream already exists"
fi

if ! stream_exists "FUNCTION_CONTROL"; then
    nats stream add FUNCTION_CONTROL \
        --subjects "function.control.>" \
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
    echo "Created FUNCTION_CONTROL stream"
fi

if ! stream_exists "FUNCTION_CONTROL_RESPONSE"; then
    nats stream add FUNCTION_CONTROL_RESPONSE \
        --subjects "function.control.response" \
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
    echo "Created FUNCTION_CONTROL_RESPONSE stream"
else
    # Purge existing messages from the stream
    nats stream purge FUNCTION_CONTROL_RESPONSE --server=nats://localhost:4222 --force
    echo "Purged existing FUNCTION_CONTROL_RESPONSE stream"
fi

if ! stream_exists "FUNCTION_OUTPUT"; then
    nats stream add FUNCTION_OUTPUT \
        --subjects "function.output" \
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
    echo "Created FUNCTION_OUTPUT stream"
else
    # Optionally purge existing messages from the stream
    nats stream purge FUNCTION_OUTPUT --server=nats://localhost:4222 --force
    echo "Purged existing FUNCTION_OUTPUT stream"
fi

# # Create RECON_DATA stream if it doesn't exist
# if ! stream_exists "RECON_DATA"; then
#     nats stream add RECON_DATA \
#         --subjects "recon.data" \
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
#     echo "Created RECON_DATA stream"
# else
#     echo "RECON_DATA stream already exists"
# fi

if ! stream_exists "RECON_DATA"; then
    nats stream add RECON_DATA \
        --subjects "recon.data" \
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
    echo "Created RECON_DATA stream"
else
    echo "RECON_DATA stream already exists"
fi

# Create LOGS_GENERAL stream if it doesn't exist
if ! stream_exists "LOGS_GENERAL"; then
    nats stream add LOGS_GENERAL \
        --subjects "logs.general" \
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
    echo "Created LOGS_GENERAL stream"
else
    echo "LOGS_GENERAL stream already exists"
fi