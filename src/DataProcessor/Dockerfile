FROM ghcr.io/h3xitsec/h3xrecon_base:latest

COPY . /app
COPY ./QueueManager /app/QueueManager
COPY ./DatabaseManager /app/DatabaseManager

#ENV NAME=DataProcessor
ENV H3XRECON_ROLE=dataprocessor

CMD ["python", "start_data_processor.py"]
