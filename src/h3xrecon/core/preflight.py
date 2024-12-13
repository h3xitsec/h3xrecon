from typing import Dict, Callable, Any
import asyncio
from loguru import logger
from .database import DatabaseManager
from .queue import QueueManager
import redis

class PreflightCheck:
    def __init__(self, config, service_name: str):
        self.config = config
        self.service_name = service_name
        self.redis_client = None
        self.db = None
        self.qm = None

    async def check_redis(self) -> bool:
        """Check Redis connectivity."""
        try:
            logger.info("Checking Redis connectivity...")
            self.redis_client = redis.Redis(
                host=self.config.redis.host,
                port=self.config.redis.port,
                db=1,
                password=self.config.redis.password
            )
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis check failed: {e}")
            return False

    async def check_nats(self) -> bool:
        """Check NATS connectivity."""
        try:
            logger.info("Checking NATS connectivity...")
            temp_qm = QueueManager(client_name=f"{self.service_name}-preflight", config=self.config.nats)
            await temp_qm.connect()
            await temp_qm.close()
            return True
        except Exception as e:
            logger.error(f"NATS check failed: {e}")
            return False

    async def check_database(self) -> bool:
        """Check Database connectivity."""
        try:
            logger.info("Checking Database connectivity...")
            temp_db = DatabaseManager()
            result = await temp_db._fetch_value("SELECT 1")
            if result.success:
                return True
            return False
        except Exception as e:
            logger.error(f"Database check failed: {e}")
            return False

    async def run_checks(self, max_attempts: int = None, retry_delay: int = 5) -> bool:
        """
        Run all preflight checks until services are ready.
        
        Args:
            max_attempts: Maximum number of attempts (None for infinite)
            retry_delay: Delay between attempts in seconds
        """
        attempt = 1
        services = {
            "Redis": self.check_redis,
            "NATS": self.check_nats,
            "Database": self.check_database
        }

        while max_attempts is None or attempt <= max_attempts:
            logger.info(f"Preflight check attempt {attempt}")
            
            all_services_ready = True
            for service_name, check_func in services.items():
                try:
                    if not await check_func():
                        logger.warning(f"{service_name} is not ready")
                        all_services_ready = False
                    else:
                        logger.success(f"{service_name} is ready")
                except Exception as e:
                    logger.error(f"Error checking {service_name}: {e}")
                    all_services_ready = False

            if all_services_ready:
                logger.success("All services are ready!")
                return True

            attempt += 1
            logger.info(f"Waiting {retry_delay} seconds before next attempt...")
            await asyncio.sleep(retry_delay)

        logger.error("Maximum preflight check attempts reached")
        return False
