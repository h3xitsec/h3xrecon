import asyncio
from QueueManager import QueueManager

async def message_handler(data):
    """Example message handler function"""
    print(f"Received message: {data}")
    # Process the message as needed
    await asyncio.sleep(0.1)  # Simulate some processing

async def main():
    qm = QueueManager()
    
    try:
        # Connect to NATS
        await qm.connect()
        
        # Subscribe to a subject
        await qm.subscribe(
            subject="function.execute",
            stream="FUNCTION_EXECUTE",
            durable_name="MY_CONSUMER",
            message_handler=message_handler,
            batch_size=1
        )
        
        # Keep the application running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        await qm.close()

if __name__ == "__main__":
    asyncio.run(main())