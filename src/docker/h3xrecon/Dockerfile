FROM python:3.9-slim

WORKDIR /app

# Install additional system dependencies
RUN apt-get update && apt-get install -y \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH="/app"

COPY h3xrecon /app/src/h3xrecon

COPY setup.py /app/setup.py

RUN cd /app && pip install .

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

RUN pip install dnspython

RUN go install -v github.com/projectdiscovery/pdtm/cmd/pdtm@latest && \
    pdtm -i subfinder && \
    pdtm -i httpx && \
    pdtm -i dnsx

RUN git clone https://github.com/UnaPibaGeek/ctfr.git /opt/ctfr && \
    cd /opt/ctfr && \
    pip install -r requirements.txt

RUN go install github.com/Josue87/gotator@latest

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]