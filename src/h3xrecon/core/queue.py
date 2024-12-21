from typing import Dict, Any, Optional, Callable, Awaitable
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy, ReplayPolicy
from nats.errors import TimeoutError as NatsTimeoutError, ConnectionClosedError
import random
from loguru import logger
import json
import asyncio
from .config import Config
from h3xrecon.__about__ import __version__
from nats.js.client import JetStreamContext
from nats.errors import ConnectionClosedError, TimeoutError, NoRespondersError
from nats.js.errors import NoStreamResponseError

class StreamUnavailableError(Exception):
    """Raised when a stream is unavailable or locked"""
    pass

class QueueManager:
    def __init__(self, client_name: str = f"unknown-{random.randint(1000, 9999)}", config: Config = None):
        """Initialize the QueueManager without connecting to NATS.
        The actual connection is established when connect() is called.
        """
        logger.debug(f"Initializing Queue Manager... (v{__version__})")
        self.nc: Optional[NATS] = None
        self.js = None
        self.client_name = client_name
        if config is None:  
            self.config = Config().nats
        else:
            self.config = config
        logger.debug(f"NATS config: {self.config.url}")
        self._subscriptions = {}
        self._subscription_subjects = {}
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 1  # Start with 1 second delay
        self._stream_retry_attempts = 3
        self._stream_retry_delay = 1

    async def connect(self) -> None:
        """Connect to NATS server using environment variables for configuration."""
        async def disconnected_cb():
            print("Got disconnected...")

        async def reconnected_cb():
            print("Got reconnected...")

        async def error_cb(e):
            print(f"Error connecting to NATS server, retrying...")

        try:
            self.nc = NATS()
            nats_server = self.config.url
            connect_options = {
                "servers": [self.config.url],
                "error_cb": error_cb,
                "disconnected_cb": disconnected_cb,
                "reconnected_cb": reconnected_cb,
                "connect_timeout": 5,  # 5 seconds timeout
                "max_reconnect_attempts": 10,
                "reconnect_time_wait": 1,  # 1 second between reconnect attempts
                "name": f"{self.client_name}-{__version__}"
            }
            await self.nc.connect(**connect_options)
            self.js = self.nc.jetstream()
            logger.debug(f"Connected to NATS server at {nats_server}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: Connection refused at {self.config.url}")
            raise ConnectionError("NATS connection failed: Connection refused") from e
    
    async def unsubscribe(self, subject: str, stream: str, durable_name: str = None):
        if self.js:
            await self.js.delete_consumer(stream, durable_name)
            logger.debug(f"Unsubscribed from {subject} on stream {stream} with durable name {durable_name}")
        else:
            logger.warning(f"No JetStream context available for unsubscribe")

    async def close(self) -> None:
        self.nc.close()

    async def ensure_connected(self) -> None:
        """Ensure NATS connection is established."""
        logger.debug("Ensuring NATS connection is established")
        if self.nc is None or not self.nc.is_connected:
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"Failed to connect to NATS: {str(e)}")
                raise
    
    async def ensure_jetstream(self) -> None:
        """Initialize JetStream if not already initialized."""
        await self.ensure_connected()
        if self.js is None:
            self.js = self.nc.jetstream()

    async def publish_message(self, subject: str, stream: str, message: Dict[str, Any], retry_count: int = 0):
        """
        Publish message with retry logic for both connection and stream issues.
        
        Args:
            subject: NATS subject
            stream: JetStream stream name
            message: Message to publish
            retry_count: Current retry attempt (used internally)
        """
        try:
            await self.ensure_connected()
            
            try:
                await self.js.publish(subject, json.dumps(message).encode())
            except NoStreamResponseError:
                logger.debug(f"No stream response for {stream}, dropping message")
                pass
                #if retry_count < self._stream_retry_attempts:
                #    logger.warning(f"Stream {stream} unavailable, attempt {retry_count + 1}/{self._stream_retry_attempts}")
                #    await asyncio.sleep(self._stream_retry_delay)
                #    return await self.publish_message(subject, stream, message, retry_count + 1)
                #else:
                #    logger.error(f"Stream {stream} unavailable after {self._stream_retry_attempts} attempts")
                #    raise StreamUnavailableError(f"Stream {stream} is unavailable or locked")
            except NoRespondersError:
                if retry_count < self._stream_retry_attempts:
                    logger.warning(f"No responders for {stream}, attempt {retry_count + 1}/{self._stream_retry_attempts}")
                    await asyncio.sleep(self._stream_retry_delay)
                    return await self.publish_message(subject, stream, message, retry_count + 1)
                else:
                    logger.error(f"No responders available for {stream} after {self._stream_retry_attempts} attempts")
                    raise StreamUnavailableError(f"No responders available for stream {stream}")
                    
        except ConnectionClosedError:
            logger.warning("NATS connection closed, attempting to reconnect...")
            await self.connect()
            if retry_count < self._stream_retry_attempts:
                return await self.publish_message(subject, stream, message, retry_count + 1)
            raise
        except StreamUnavailableError as e:
            logger.debug(f"Stream {stream} unavailable: {str(e)}")
            pass
        except Exception as e:
            logger.error(f"Error publishing message: {str(e)}")
            raise

    async def ensure_stream_exists(self, stream: str) -> bool:
        """
        Verify that a stream exists and is available.
        
        Args:
            stream: Name of the stream to check
            
        Returns:
            bool: True if stream exists and is available
        """
        try:
            await self.ensure_connected()
            stream_info = await self.js.stream_info(stream)
            return True
        except NoStreamResponseError:
            return False
        except Exception as e:
            logger.error(f"Error checking stream {stream}: {str(e)}")
            return False

    async def wait_for_stream(self, stream: str, timeout: int = 30) -> bool:
        """
        Wait for a stream to become available.
        
        Args:
            stream: Name of the stream to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if stream became available, False if timeout reached
        """
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if await self.ensure_stream_exists(stream):
                return True
            await asyncio.sleep(1)
        return False

    async def subscribe(self, 
                       subject: str,
                       stream: str,
                       message_handler: Callable[[Any], Awaitable[None]],
                       durable_name: str = None,
                       batch_size: int = 1,
                       queue_group: str = None,
                       consumer_config: Optional[Dict[str, Any]] = None,
                       broadcast: bool = False) -> None:
        """
        Subscribe to a subject using push-based subscription and process messages using the provided handler.
        """
        await self.ensure_jetstream()
        
        # Default consumer configuration
        default_config = ConsumerConfig(
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.NONE if broadcast else AckPolicy.EXPLICIT,
            replay_policy=ReplayPolicy.INSTANT,
            max_deliver=1,
            ack_wait=30,
            filter_subject=subject,
            deliver_group=queue_group
        )

        # Update with custom config if provided
        if consumer_config:
            default_config = ConsumerConfig(**{**default_config.__dict__, **consumer_config})

        try:
            # Create message callback
            cb = await self._message_callback(message_handler)
            
            # Create push subscription
            subscription = await self.js.subscribe(
                subject,
                queue=queue_group,
                durable=durable_name if not broadcast else None,
                stream=stream,
                config=default_config,
                cb=cb
            )
            
            # Store subscription and its subject for cleanup and reference
            sub_key = f"{stream}:{subject}:{durable_name if not broadcast else 'broadcast'}"
            self._subscriptions[sub_key] = subscription
            self._subscription_subjects[subscription] = subject
            
            logger.debug(f"{await subscription.consumer_info()}")
            logger.debug(f"Subscribed to '{subject}' on stream '{stream}' with {'broadcast mode' if broadcast else f'durable name {durable_name}'}")
            return subscription
            
        except Exception as e:
            logger.error(f"Failed to create subscription: {e}")
            raise

    async def _message_callback(self, handler):
        async def cb(msg):
            try:
                logger.debug(f"Received message: {msg.data}")
                await handler(msg)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                logger.exception(e)
        return cb

    async def close(self) -> None:
        """Close the NATS connection and clean up resources."""
        if self.nc and self.nc.is_connected:
            await self.nc.drain()
            await self.nc.close()
            logger.debug("NATS connection closed")

    async def _error_callback(self, e):
        logger.error(f"NATS error: {str(e)}")

    async def _reconnected_callback(self):
        logger.info("Reconnected to NATS")
        self.js = self.nc.jetstream()

    async def _disconnected_callback(self):
        logger.warning("Disconnected from NATS")

    async def _closed_callback(self):
        logger.warning("NATS connection closed")