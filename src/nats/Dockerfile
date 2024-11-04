FROM nats:2.10.21-alpine

# Install wget to download nats cli
RUN apk add --no-cache wget

# Download and install NATS CLI
RUN wget https://github.com/nats-io/natscli/releases/download/v0.1.5/nats-0.1.5-linux-amd64.zip \
    && unzip nats-0.1.5-linux-amd64.zip \
    && mv nats-0.1.5-linux-amd64/nats /usr/local/bin/ \
    && rm -rf nats-0.1.5-linux-amd64*

# Copy scripts
COPY ./init.sh /init.sh
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /init.sh /entrypoint.sh

CMD ["/entrypoint.sh"]