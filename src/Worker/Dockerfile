FROM ghcr.io/h3xitsec/h3xrecon_base:latest

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

RUN go install github.com/Josue87/gotator@latest

COPY . /app

ENV NAME=Worker

CMD ["python", "start_worker.py"]
