FROM python:3.9-slim

WORKDIR /app

# Install additional system dependencies
RUN apt-get update && apt-get install -y \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="$PATH:/root/go/bin:/root/.pdtm/go/bin:/usr/lib/go-1.15/bin"

RUN apt-get update && apt-get install -y \
    git \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/h3xitsec/h3xrecon-cli.git /app/h3xrecon-cli && \
    python3 -m venv /app/venv && \
    cd /app/h3xrecon-cli && \
    /app/venv/bin/pip install .

ENTRYPOINT ["/app/venv/bin/python3", "-m", "h3xrecon_cli.main"]

CMD ["-h"]