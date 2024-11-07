import asyncio
from loguru import logger
from new_src.h3xrecon.dataprocessor.base import DataProcessor
from h3xrecon.core.config import Config

async def main():
    config = Config()
    config.setup_logging()
    logger.info("Starting H3XRecon Data Processor...")
    data_processor = DataProcessor(config)
    print(config.to_dict())
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
