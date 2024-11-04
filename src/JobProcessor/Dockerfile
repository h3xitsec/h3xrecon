FROM 127.0.0.1:5000/base:latest

COPY ./JobProcessor /app/JobProcessor
COPY ./QueueManager /app/QueueManager

ENV NAME=JobProcessor

CMD ["python", "./JobProcessor/start_job_processor.py"]
