FROM ghcr.io/h3xitsec/h3xrecon_base:latest

WORKDIR /app

# Install dependencies
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app
COPY ./DatabaseManager /app/DatabaseManager
COPY ./QueueManager /app/QueueManager

# Command to run the application
CMD ["python", "Logger.py"]