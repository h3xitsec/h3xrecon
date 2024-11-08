#!/bin/bash

echo "Starting entrypoint script"
echo "H3XRECON_ROLE=${H3XRECON_ROLE}"

# Force Python to run in unbuffered mode and forward all output
export PYTHONUNBUFFERED=1

if [ "$H3XRECON_ROLE" == "worker" ]; then
    echo "Starting worker"
    exec python3 -u -m h3xrecon.workers.main
elif [ "$H3XRECON_ROLE" == "dataprocessor" ]; then
    echo "Starting dataprocessor"
    exec python3 -u -m h3xrecon.dataprocessor.main
elif [ "$H3XRECON_ROLE" == "jobprocessor" ]; then
    echo "Starting jobprocessor"
    exec python3 -u -m h3xrecon.jobprocessor.main
elif [ "$H3XRECON_ROLE" == "logging" ]; then
    echo "Starting logging"
    exec python3 -u -m h3xrecon.logging.main
else
    echo "Starting default"
    exec python3 -u -m h3xrecon.cli.main
fi
