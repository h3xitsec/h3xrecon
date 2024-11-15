FROM python:3.9-slim

WORKDIR /app

# Install additional system dependencies
RUN apt-get update && apt-get install -y \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="$PATH:/root/go/bin:/root/.pdtm/go/bin:/usr/lib/go-1.15/bin"

RUN apt-get update && apt-get install -y \
    git \
    golang-go \
    jq \
    prips \
    nmap \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN git clone -b 5-move-functions-output-processing-function-into-the-plugin-that-the-jobprocessor-will-use https://github.com/h3xitsec/h3xrecon-server.git /app/h3xrecon-server && \
    python3 -m venv /app/venv && \
    cd /app/h3xrecon-server && \
    /app/venv/bin/pip install .

COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1

ENV PYTHONFAULTHANDLER=1

CMD ["/entrypoint.sh"]