FROM ghcr.io/h3xitsec/h3xrecon_base:latest

COPY ./DataProcessor /app/DataProcessor
COPY ./QueueManager /app/QueueManager

ENV NAME=DataProcessor

CMD ["python", "./DataProcessor/start_data_processor.py"]
