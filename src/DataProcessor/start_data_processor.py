import asyncio
from loguru import logger
from DataProcessor import DataProcessor

async def main():
    data_processor = DataProcessor()
    await data_processor.start()
    
    try:
        # Keep the data processor running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await data_processor.stop()

if __name__ == "__main__":
    asyncio.run(main())
