from typing import Dict, Any, Optional, Callable, Awaitable
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy, ReplayPolicy
from nats.errors import TimeoutError as NatsTimeoutError
from loguru import logger
import json
import asyncio
from .config import Config
from h3xrecon.__about__ import __version__

class QueueManager:
    def __init__(self, config: Config = None):
        """Initialize the QueueManager without connecting to NATS.
        The actual connection is established when connect() is called.
        """
        logger.debug(f"Initializing Queue Manager... (v{__version__})")
        self.nc: Optional[NATS] = None
        self.js = None
        if config is None:  
            self.config = Config().nats
        else:
            self.config = config
        logger.debug(f"NATS config: {self.config.url}")
        self._subscriptions = {}
    
    async def connect(self) -> None:
        """Connect to NATS server using environment variables for configuration."""
        try:
            self.nc = NATS()
            nats_server = self.config.url
            await self.nc.connect(servers=[nats_server])
            self.js = self.nc.jetstream()
            logger.debug(f"Connected to NATS server at {nats_server}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: Connection refused at {self.config.url}")
            raise ConnectionError("NATS connection failed: Connection refused") from e

    async def close(self) -> None:
        self.nc.close()

    async def ensure_connected(self) -> None:
        """Ensure NATS connection is established."""
        logger.debug("Ensuring NATS connection is established")
        if self.nc is None or not self.nc.is_connected:
            await self.connect()
    
    async def ensure_jetstream(self) -> None:
        """Initialize JetStream if not already initialized."""
        await self.ensure_connected()
        if self.js is None:
            self.js = self.nc.jetstream()

    async def get_stream_info(self, stream_name: str = None):
        """Get information about NATS streams"""
        try:

            
            await self.ensure_connected()
            js = self.nc.jetstream()
            if stream_name:
                # Get info for specific stream
                stream = await js.stream_info(stream_name)
                consumers = await js.consumers_info(stream_name)
                
                # Calculate unprocessed messages across all consumers
                unprocessed_messages = 0
                for consumer in consumers:
                    unprocessed_messages += consumer.num_pending
                
                return [{
                    "stream": stream.config.name,
                    "subjects": stream.config.subjects,
                    "messages": stream.state.messages,
                    "bytes": stream.state.bytes,
                    "consumer_count": stream.state.consumer_count,
                    "unprocessed_messages": unprocessed_messages,
                    "first_seq": stream.state.first_seq,
                    "last_seq": stream.state.last_seq,
                    "deleted_messages": stream.state.deleted,
                    "storage_type": stream.config.storage,
                    "retention_policy": stream.config.retention,
                    "max_age": stream.config.max_age
                }]
            else:
                # Get info for all streams
                streams = await js.streams_info()
                result = []
                for s in streams:
                    consumers = await js.consumers_info(s.config.name)
                    unprocessed_messages = sum(c.num_pending for c in consumers)
                    
                    result.append({
                        "stream": s.config.name,
                        "subjects": s.config.subjects,
                        "messages": s.state.messages,
                        "bytes": s.state.bytes,
                        "consumer_count": s.state.consumer_count,
                        "unprocessed_messages": unprocessed_messages,
                        "first_seq": s.state.first_seq,
                        "last_seq": s.state.last_seq,
                        "deleted_messages": s.state.deleted,
                        "storage_type": s.config.storage,
                        "retention_policy": s.config.retention,
                        "max_age": s.config.max_age
                    })
                return result
        except Exception as e:
            print(f"NATS connection error: {str(e)}")
            return []
        finally:
            try:
                await self.nc.close()
            except:
                pass
    
    async def get_stream_messages(self, stream_name: str, subject: str = None, batch_size: int = 100):
        """Get messages from a specific NATS stream"""
        try:
            await self.ensure_connected()
            js = self.nc.jetstream()
            # Create a consumer with explicit configuration
            consumer_config = {
                "deliver_policy": "all",  # Get all messages
                "ack_policy": "explicit",
                "replay_policy": "instant",
                "inactive_threshold": 300000000000  # 5 minutes in nanoseconds
            }
            # If subject is provided, use it for subscription
            subscribe_subject = subject if subject else ">"
            
            consumer = await js.pull_subscribe(
                subscribe_subject,
                durable=None,
                stream=stream_name
            )
            messages = []
            try:
                # Fetch messages
                fetched = await consumer.fetch(batch_size)
                for msg in fetched:
                    # Get stream info for message counts
                    stream_info = await js.stream_info(stream_name)
                    message_data = {
                        'subject': msg.subject,
                        'data': msg.data.decode() if msg.data else None,
                        'sequence': msg.metadata.sequence.stream if msg.metadata else None,
                        'time': msg.metadata.timestamp if msg.metadata else None,
                        'delivered_count': msg.metadata.num_delivered if msg.metadata else None,
                        'pending_count': msg.metadata.num_pending if msg.metadata else None,
                        'stream_total': stream_info.state.messages if stream_info.state else None,
                        'is_redelivered': msg.metadata.num_delivered > 1 if msg.metadata else False
                    }
                    messages.append(message_data)
                    
            except Exception as e:
                print(f"Error fetching messages: {str(e)}")
            
            return messages
            
        except Exception as e:
            print(f"NATS connection error: {str(e)}")
            return []
        finally:
            try:
                await self.nc.close()
            except:
                pass
    
    async def flush_stream(self, stream_name: str):
        """Flush all messages from a NATS stream
        Args:
            stream_name (str): Name of the stream to flush
        """
        try:
            await self.ensure_connected()
            js = self.nc.jetstream()
            
            try:
                # Purge all messages from the stream
                await js.purge_stream(stream_name)
                return {"status": "success", "message": f"Stream {stream_name} flushed successfully"}
            except Exception as e:
                return {"status": "error", "message": f"Error flushing stream: {str(e)}"}
            
        except Exception as e:
            return {"status": "error", "message": f"NATS connection error: {str(e)}"}
        finally:
            try:
                await self.nc.close()
            except:
                pass
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
            
            logger.debug(f"Subscribed to '{subject}' on stream '{stream}' with durable name '{durable_name}'")
            
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
                            
                    except Exception:
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
            logger.debug("NATS connection closed")