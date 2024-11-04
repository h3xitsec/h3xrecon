FROM 127.0.0.1:5000/base:latest

COPY . /app/
COPY ./QueueManager /app/QueueManager

ENV NAME=JobProcessor

CMD ["python", "./start_job_processor.py"]
