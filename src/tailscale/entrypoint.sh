#!/bin/sh
# Read the secret file and set it as an environment variable
export TS_AUTH_KEY=$(cat /run/secrets/tailscale_auth_key)

# Start the original entrypoint/command
exec /usr/local/bin/containerboot