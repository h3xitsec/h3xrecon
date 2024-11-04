FROM ghcr.io/h3xitsec/h3xrecon_base:latest

COPY . /app
COPY ./DatabaseManager /app/DatabaseManager
COPY ./QueueManager /app/QueueManager

ENV NAME=JobProcessor

CMD ["python", "start_job_processor.py"]
