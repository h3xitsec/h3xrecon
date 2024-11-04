import asyncio
from Worker import Worker
from loguru import logger

async def main():
    worker = Worker()
    await worker.start()

    try:
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())