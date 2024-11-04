# Use an official Python runtime as a parent image
FROM python:3.9.16-slim

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

ENV PATH="$PATH:/root/go/bin:/root/.pdtm/go/bin:/usr/lib/go-1.15/bin"

# Install additional system dependencies
RUN apt-get update && apt-get install -y \
    git \
    golang-1.15 \
    jq \
    prips \
    nmap \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install dnspython

RUN mkdir -p /root/.pdtm/go/bin && \
    wget https://github.com/projectdiscovery/pdtm/releases/download/v0.0.9/pdtm_0.0.9_linux_arm64.zip -O /tmp/pdtm.zip &&\
    unzip /tmp/pdtm.zip && \
    mv pdtm /root/.pdtm/go/bin/pdtm && \
    pdtm -i subfinder && \
    pdtm -i httpx && \
    pdtm -i dnsx

RUN git clone https://github.com/UnaPibaGeek/ctfr.git /opt/ctfr && \
    cd /opt/ctfr && \
    pip install -r requirements.txt

ENV GOROOT=/usr/lib/go-1.15
ENV GO111MODULE=on

RUN go get github.com/Josue87/gotator@latest

COPY . /app

ENV NAME=Worker

# Run worker.py when the container launches
CMD ["python", "start_worker.py"]
