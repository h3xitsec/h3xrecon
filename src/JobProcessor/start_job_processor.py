import asyncio
from loguru import logger
from JobProcessor import JobProcessor

async def main():
    job_processor = JobProcessor()
    await job_processor.start()
    
    try:
        # Keep the server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await job_processor.stop()

if __name__ == "__main__":
    asyncio.run(main())
