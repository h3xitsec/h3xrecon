FROM ghcr.io/h3xitsec/h3xrecon_base:latest

COPY . /app
COPY ./QueueManager /app/QueueManager
COPY ./DatabaseManager /app/DatabaseManager

ENV NAME=Client

RUN pip install -r /app/requirements.txt

ENTRYPOINT ["python", "/app/client.py"]
