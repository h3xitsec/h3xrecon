"""
Main entry point for the H3XRecon worker component.
"""

import asyncio
from loguru import logger
from h3xrecon.core.config import Config
from h3xrecon.workers.base import Worker

async def main():
    # Load configuration
    config = Config()
    config.setup_logging()
    logger.info("Starting H3XRecon worker...")

    # Initialize and start worker
    worker = Worker(config)
    
    try:
        await worker.start()
        
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")
        await worker.stop()
    except Exception as e:
        logger.exception(f"Worker error: {e}")
        raise
    finally:
        logger.info("Worker shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())