FROM 127.0.0.1:5000/base:latest

COPY ./DataProcessor /app/DataProcessor
COPY ./QueueManager /app/QueueManager

ENV NAME=DataProcessor

CMD ["python", "./DataProcessor/start_data_processor.py"]
