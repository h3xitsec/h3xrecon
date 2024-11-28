#!/usr/bin/env bash

# Extract the VERSION from __about__.py using grep with Perl regex
VERSION=$(grep -oP '(?<=__version__ = ").*(?=")' ./src/h3xrecon/__about__.py)

# Check if VERSION extraction was successful
if [[ -z "$VERSION" ]]; then
    echo "Failed to extract VERSION. Exiting."
    exit 1
fi

echo "Building worker version ${VERSION}"
docker build --build-arg VERSION=${VERSION} -t ghcr.io/h3xitsec/h3xrecon/worker:${VERSION} -f ./Dockerfile.worker .
