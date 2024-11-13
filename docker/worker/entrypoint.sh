#!/bin/bash
export PYTHONUNBUFFERED=1
export PYTHONPATH=/app:$PYTHONPATH

echo "Starting worker"
/app/venv/bin/python -m h3xrecon_worker.main