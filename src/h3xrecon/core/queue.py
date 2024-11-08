from typing import Dict, Any, Optional, Callable, AsyncGenerator, Awaitable
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy, ReplayPolicy
from nats.errors import TimeoutError as NatsTimeoutError
from loguru import logger
import json
import asyncio
from datetime import datetime, timezone
from .config import Config

class QueueManager:
    def __init__(self, config: Config = None):
        """Initialize the QueueManager without connecting to NATS.
        The actual connection is established when connect() is called.
        """
        self.nc: Optional[NATS] = None
        self.js = None
        if config is None:
            self.config = Config().nats
        else:
            self.config = config
        self._subscriptions = {}
    
    async def connect(self) -> None:
        """Connect to NATS server using environment variables for configuration."""
        try:
            self.nc = NATS()
            nats_server = self.config.url
            await self.nc.connect(servers=[nats_server])
            logger.info(f"Connected to NATS server at {nats_server}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise
    async def close(self) -> None:
        self.nc.close()

    async def ensure_connected(self) -> None:
        """Ensure NATS connection is established."""
        if self.nc is None or not self.nc.is_connected:
            await self.connect()
    
    async def ensure_jetstream(self) -> None:
        """Initialize JetStream if not already initialized."""
        await self.ensure_connected()
        if self.js is None:
            self.js = self.nc.jetstream()

    async def publish_message(self, subject: str, stream: str, message: Any) -> None:
        """
        Publish a message to a specific subject and stream.
        
        Args:
            subject: The subject to publish to
            stream: The stream name
            message: The message to publish (will be JSON encoded)
        """
        await self.ensure_jetstream()
        try:
            payload = json.dumps(message) if not isinstance(message, str) else message
            await self.js.publish(
                subject,
                payload.encode(),
                stream=stream
            )
            logger.debug(f"Published message to {subject} on stream {stream}\nMessage:\n{json.dumps(json.loads(payload), indent=4)}")
        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            raise

    async def subscribe(self, 
                       subject: str,
                       stream: str,
                       durable_name: str,
                       message_handler: Callable[[Any], Awaitable[None]],
                       batch_size: int = 1,
                       consumer_config: Optional[Dict[str, Any]] = None) -> None:
        """
        Subscribe to a subject and process messages using the provided handler.
        
        Args:
            subject: The subject to subscribe to
            stream: The stream name
            durable_name: Durable name for the consumer
            message_handler: Async function to handle received messages
            batch_size: Number of messages to fetch in each batch
            consumer_config: Optional custom consumer configuration
        """
        await self.ensure_jetstream()
        
        # Default consumer configuration
        default_config = ConsumerConfig(
            durable_name=durable_name,
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            replay_policy=ReplayPolicy.INSTANT,
            max_deliver=1,
            ack_wait=30,
            filter_subject=subject
        )

        # Update with custom config if provided
        if consumer_config:
            default_config = ConsumerConfig(**{**default_config.__dict__, **consumer_config})

        try:
            # Create pull subscription
            subscription = await self.js.pull_subscribe(
                subject,
                durable_name,
                stream=stream,
                config=default_config
            )
            
            # Store subscription for cleanup
            self._subscriptions[f"{stream}:{subject}:{durable_name}"] = subscription
            
            # Start message processing
            asyncio.create_task(self._process_messages(
                subscription, 
                message_handler, 
                batch_size
            ))
            
            logger.info(f"Subscribed to '{subject}' on stream '{stream}' with durable name '{durable_name}'")
            
        except Exception as e:
            logger.error(f"Failed to create subscription: {e}")
            raise

    async def _process_messages(self,
                              subscription,
                              message_handler: Callable[[Any], Awaitable[None]],
                              batch_size: int) -> None:
        """
        Process messages from a subscription.
        
        Args:
            subscription: The NATS subscription object
            message_handler: Async function to handle received messages
            batch_size: Number of messages to fetch in each batch
        """
        while True:
            try:
                messages = await subscription.fetch(batch=batch_size, timeout=1)
                
                for msg in messages:
                    try:
                        #logger.debug(f"Processing message sequence: {msg.metadata.sequence}")

                        # Parse message data
                        data = json.loads(msg.data.decode())
                        
                        # Process message
                        await message_handler(data)
                        
                        # Acknowledge message
                        if not msg._ackd:
                            await msg.ack()
                            #logger.debug(f"Message {msg.metadata.sequence} acknowledged")
                            
                    except Exception as e:
                        #logger.error(f"Error processing message {msg.metadata.sequence}: {e}")
                        if not msg._ackd:
                            await msg.nak()
                            #logger.debug(f"Message {msg.metadata.sequence} negative acknowledged")
                            
            except NatsTimeoutError:
                await asyncio.sleep(0.1)
                continue
            except Exception as e:
                logger.error(f"Error in message processing loop: {e}")
                await asyncio.sleep(0.1)

    async def close(self) -> None:
        """Close the NATS connection and clean up resources."""
        if self.nc and self.nc.is_connected:
            await self.nc.drain()
            await self.nc.close()
            logger.info("NATS connection closed")