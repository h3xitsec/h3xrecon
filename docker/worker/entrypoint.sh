#!/bin/bash
export PYTHONUNBUFFERED=1
export PYTHONPATH=/app:$PYTHONPATH

echo "Starting worker"
source /app/venv/bin/activate
exec h3xrecon-worker