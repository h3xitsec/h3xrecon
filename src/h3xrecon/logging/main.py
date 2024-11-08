import asyncio
from loguru import logger
from h3xrecon.logging import LoggingService
from h3xrecon.core.config import Config

async def main():
    config = Config()
    config.setup_logging()
    logger.info("Starting H3XRecon Logger...")
    logging_service = LoggingService(config)
    await logging_service.start()
    
    try:
        # Keep the data processor running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await logging_service.stop()

if __name__ == "__main__":
    asyncio.run(main())
