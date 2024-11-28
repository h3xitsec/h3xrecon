#!/usr/bin/env bash

# Build the Python package
rm -rf ./dist
python -m hatchling build

# Extract the VERSION from __about__.py using grep with Perl regex
VERSION=$(grep -oP '(?<=__version__ = ").*(?=")' ./src/h3xrecon/__about__.py)
# Check if VERSION extraction was successful
if [[ -z "$VERSION" ]]; then
    echo "Failed to extract VERSION. Exiting."
    exit 1
fi

echo "Building server version ${VERSION}"

# Build the Docker image with the VERSION build argument
docker build -t ghcr.io/h3xitsec/h3xrecon/server:${VERSION} \
             -f ./Dockerfile.server .
