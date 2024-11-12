#!/bin/bash
export PYTHONUNBUFFERED=1
export PYTHONPATH=/app:$PYTHONPATH

if [ -z "$H3XRECON_ROLE" ]; then
    echo "H3XRECON_ROLE is not set"
    exit 1
fi

echo "Starting server with role ${H3XRECON_ROLE}"
source /app/venv/bin/activate
exec h3xrecon-${H3XRECON_ROLE}