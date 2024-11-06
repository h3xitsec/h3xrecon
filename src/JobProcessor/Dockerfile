FROM ghcr.io/h3xitsec/h3xrecon_base:latest

COPY . /app
COPY ./QueueManager /app/QueueManager
COPY ./DatabaseManager /app/DatabaseManager

#ENV NAME=JobProcessor

ENV H3XRECON_ROLE=jobprocessor

CMD ["python", "start_job_processor.py"]
