# Use an official Python runtime as a parent image
FROM python:3.9-slim

WORKDIR /app

# Install additional system dependencies
RUN apt-get update && apt-get install -y \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

ENV PYTHONPATH="/app"

RUN pip install \
        --upgrade \
        --trusted-host pypi.org \
        --trusted-host pypi.python.org \
        --trusted-host files.pythonhosted.org \
        --no-cache-dir \
        -r requirements.txt