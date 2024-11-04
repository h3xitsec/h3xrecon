FROM ghcr.io/h3xitsec/h3xrecon_base:latest

COPY . /app
COPY ./DatabaseManager /app/DatabaseManager
COPY ./QueueManager /app/QueueManager

ENV NAME=DataProcessor

CMD ["python", "start_data_processor.py"]
