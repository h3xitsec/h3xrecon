from h3xrecon.core import DatabaseManager
from h3xrecon.core import Config
from h3xrecon.core import QueueManager
from h3xrecon.core import PreflightCheck
from h3xrecon.core.queue import StreamUnavailableError
from h3xrecon.__about__ import __version__
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, List, Callable
from loguru import logger
from urllib.parse import urlparse 
import time
import os
import traceback
import json
import socket
import sys
from datetime import datetime, timezone, timedelta
from enum import Enum
import psutil
import platform


@dataclass
class JobConfig:
    function: str
    param_map: Callable[[Any], Dict[str, Any]]

# Job mapping configuration
JOB_MAPPING: Dict[str, List[JobConfig]] = {
    "domain": [
        JobConfig(function="test_domain_catchall", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="resolve_domain", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="test_http", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="nuclei", param_map=lambda result: {"target": result.lower(), "extra_params": ["-as"]}),
        # JobConfig(function="find_subdomains_subfinder", param_map=lambda result: {"target": result}),
        #JobConfig(function="find_subdomains_ctfr", param_map=lambda result: {"target": result})
    ],
    "ip": [
        JobConfig(function="reverse_resolve_ip", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="port_scan", param_map=lambda result: {"target": result.lower()})
    ]
}

class ProcessorState(Enum):
    RUNNING = "running"
    PAUSED = "paused"

class DataProcessor:
    def __init__(self, config: Config):
        self.config = config
        self.qm = QueueManager(client_name="dataprocessor", config=config.nats)
        self.db_manager = DatabaseManager() #config.database.to_dict())
        self.dataprocessor_id = f"dataprocessor-{socket.gethostname()}"
        self.data_type_processors = {
            "ip": self.process_ip,
            "domain": self.process_domain,
            "url": self.process_url,
            "service": self.process_service,
            "nuclei": self.process_nuclei,
            "certificate": self.process_certificate
        }
        self._last_message_time = None
        self._health_check_task = None
        self.running = asyncio.Event()
        self.running.set()  # Start in running state
        self.state = ProcessorState.RUNNING
        self.control_subscription = None
        self.data_subscription = None

    async def _setup_subscription(self, subject: str, stream: str, message_handler: Callable, 
                                broadcast: bool = False, queue_group: str = None):
        """Helper method to setup NATS subscriptions with consistent configuration."""
        try:
            subscription = await self.qm.subscribe(
                subject=subject,
                stream=stream,
                message_handler=message_handler,
                durable_name=None,
                batch_size=1,
                queue_group=queue_group,
                consumer_config={
                    'ack_policy': AckPolicy.EXPLICIT,
                    'deliver_policy': DeliverPolicy.ALL,
                    'replay_policy': ReplayPolicy.INSTANT,
                    'max_deliver': 1
                },
                broadcast=broadcast
            )
            return subscription
        except Exception as e:
            logger.error(f"Failed to setup subscription: {e}")
            raise

    async def start(self):
        logger.info(f"Starting Data Processor (ID: {self.dataprocessor_id}) version {__version__}...")
        try:
            # Run preflight checks
            preflight = PreflightCheck(self.config, f"dataprocessor-{self.dataprocessor_id}")
            if not await preflight.run_checks():
                raise ConnectionError("Preflight checks failed. Cannot start data processor.")

            # Initialize components with retry logic
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                try:
                    await self.qm.connect()
                    # Store the subscription object
                    self.data_subscription = await self._setup_subscription(
                        subject="recon.data",
                        stream="RECON_DATA",
                        message_handler=self.message_handler,
                        queue_group="dataprocessor"
                    )
                    logger.info(f"Data Processor started and listening for messages...")
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        raise e
                    await asyncio.sleep(1)

            # Subscribe to broadcast messages (all components)
            await self.qm.subscribe(
                subject="function.control.all",
                stream="FUNCTION_CONTROL",
                durable_name=f"CONTROL_ALL_{self.dataprocessor_id}2",
                message_handler=self.control_message_handler,
                batch_size=1,
                consumer_config={
                    'ack_policy': AckPolicy.EXPLICIT,
                    'deliver_policy': DeliverPolicy.NEW,
                    'replay_policy': ReplayPolicy.INSTANT
                },
                broadcast=True
            )

            # Subscribe to broadcast messages (all dataprocessors)
            await self.qm.subscribe(
                subject="function.control.all_dataprocessor",
                stream="FUNCTION_CONTROL",
                durable_name=f"CONTROL_ALL_DATAPROCESSOR_{self.dataprocessor_id}",
                message_handler=self.control_message_handler,
                batch_size=1,
                consumer_config={
                    'ack_policy': AckPolicy.EXPLICIT,
                    'deliver_policy': DeliverPolicy.NEW,
                    'replay_policy': ReplayPolicy.INSTANT
                },
                broadcast=True
            )
            
            # Subscribe to dataprocessor-specific messages
            await self.qm.subscribe(
                subject=f"function.control.{self.dataprocessor_id}",
                stream="FUNCTION_CONTROL",
                durable_name=f"CONTROL_{self.dataprocessor_id}",
                message_handler=self.control_message_handler,
                batch_size=1,
                consumer_config={
                    'ack_policy': AckPolicy.EXPLICIT,
                    'deliver_policy': DeliverPolicy.NEW,
                    'replay_policy': ReplayPolicy.INSTANT
                },
                broadcast=True
            )

            # Start health check
            self._health_check_task = asyncio.create_task(self._health_check())
        except Exception as e:
            logger.error(f"Failed to start data processor: {str(e)}")
            sys.exit(1)

    async def stop(self):
        logger.info("Shutting down...")

    async def message_handler(self, raw_msg):
        msg = json.loads(raw_msg.data.decode())
        if self.state == ProcessorState.PAUSED:
            await raw_msg.nak()
            return
        self._last_message_time = datetime.now(timezone.utc)
        logger.debug(f"Incoming message:\nObject Type: {type(msg)} : {json.dumps(msg)}")
        try:
            if isinstance(msg.get("data"), list):
                data_item = msg.get("data")[0]
            else:
                data_item = msg.get("data")
            if isinstance(data_item, dict) and data_item.get("data_type") == "url":
                data_item = data_item.get("data").get("url")
            processor = self.data_type_processors.get(msg.get("data_type"))
            if processor:
                await processor(msg)
                await raw_msg.ack()
            else:
                logger.error(f"No processor found for data type: {msg.get('data_type')}")
                await raw_msg.nak()
                return

        except Exception as e:
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            file_name = error_location.filename.split('/')[-1]
            line_number = error_location.lineno
            logger.error(f"Error in {file_name}:{line_number} - {type(e).__name__}: {str(e)}")
            logger.exception(e)
    
    async def trigger_new_jobs(self, program_id: int, data_type: str, result: Any):
        # Check if processor is paused before triggering new jobs
        if self.state == ProcessorState.PAUSED:
            logger.info("Processor is paused, skipping triggering new jobs")
            return

        if os.getenv("H3XRECON_NO_NEW_JOBS", "false").lower() == "true":
            logger.info("H3XRECON_NO_NEW_JOBS is set. Skipping triggering new jobs.")
            return

        # Check if the data is in the program scope, if it is a domain
        if data_type == "domain":
            is_in_scope = await self.db_manager.check_domain_regex_match(result, program_id)
        else:
            is_in_scope = True
        if not is_in_scope:
            logger.info(f"Data {result} of type {data_type} is not in scope for program {program_id}. Skipping new jobs.")
            return

        if data_type in JOB_MAPPING:
            for job in JOB_MAPPING[data_type]:
                new_job = {
                    "function": job.function,
                    "program_id": program_id,
                    "params": job.param_map(result)
                }
                logger.info(f"Triggering {job.function} for {result}")
                try:
                    await self.qm.publish_message(
                        subject="function.execute",
                        stream="FUNCTION_EXECUTE",
                        message=new_job
                    )
                except StreamUnavailableError as e:
                    logger.error(f"Failed to trigger job - stream unavailable: {str(e)}")
                    # Optionally store failed jobs for retry
                    # await self.store_failed_job(new_job)
                    break  # Stop triggering more jobs if stream is unavailable
                except Exception as e:
                    logger.error(f"Failed to trigger job: {str(e)}")
                    raise

                # Instead of awaiting sleep directly, create a background task
                current_job_index = JOB_MAPPING[data_type].index(job)
                if current_job_index < len(JOB_MAPPING[data_type]) - 1:
                    logger.debug("scheduling next job trigger in 10 seconds")
                    # Create background task for the delay
                    asyncio.create_task(self._delay_next_job(program_id, data_type, result, current_job_index + 1))
                    break  # Exit the loop as remaining jobs will be handled by the background task

    async def _delay_next_job(self, program_id: int, data_type: str, result: Any, next_job_index: int):
        """Helper method to handle delayed job triggering"""
        # Check state before proceeding with delayed job
        if self.state == ProcessorState.PAUSED:
            logger.info("Processor is paused, skipping delayed job trigger")
            return

        await asyncio.sleep(5)
        job = JOB_MAPPING[data_type][next_job_index]
        new_job = {
            "function": job.function,
            "program_id": program_id,
            "params": job.param_map(result)
        }
        logger.info(f"Triggering delayed job {job.function} for {result}")
        await self.qm.publish_message(subject="function.execute", stream="FUNCTION_EXECUTE", message=new_job)
        
        # Schedule next job if there are more
        if next_job_index < len(JOB_MAPPING[data_type]) - 1:
            logger.debug("scheduling next job trigger in 10 seconds")
            asyncio.create_task(self._delay_next_job(program_id, data_type, result, next_job_index + 1))

    ################################
    ## Data processing functions ##
    ################################

    async def process_ip(self, msg_data: Dict[str, Any]):
        if msg_data.get('attributes') == None:
            attributes = {}
        else:
            attributes = msg_data.get('attributes')
        for ip in msg_data.get('data'):
            ptr = attributes.get('ptr')
            if isinstance(ptr, list):
                ptr = ptr[0] if ptr else None  # Take the first PTR record if it's a list
            elif ptr == '':
                ptr = None  # Set empty string to None
            cloud_provider = attributes.get('cloud_provider', None)
            result = await self.db_manager.insert_ip(ip=ip, ptr=ptr, cloud_provider=cloud_provider, program_id=msg_data.get('program_id'))
            logger.debug(result)
            # Check if operation was successful, regardless of inserted/updated status
            if result.success:
                await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="ip", result=ip)
    
    async def process_domain(self, msg_data: Dict[str, Any]):
        for domain in msg_data.get('data'):
            logger.info(f"Processing domain: {domain}")
            if not await self.db_manager.check_domain_regex_match(domain, msg_data.get('program_id')):
                logger.info(f"Domain {domain} is not part of program {msg_data.get('program_id')}. Skipping processing.")
                continue
            else:
                # Get existing domain data first
                existing_domain = await self.db_manager.get_domain(domain)
                
                # Get attributes with defaults from existing data
                if msg_data.get('attributes') is None:
                    attributes = {}
                else:
                    attributes = msg_data.get('attributes')
                
                # Only update is_catchall if explicitly provided
                is_catchall = attributes.get('is_catchall', existing_domain.get('is_catchall', False) if existing_domain else False)
                
                inserted = await self.db_manager.insert_domain(
                    domain=domain, 
                    ips=attributes.get('ips', []), 
                    cnames=attributes.get('cnames', []), 
                    is_catchall=is_catchall,
                    program_id=msg_data.get('program_id')
                )
                if inserted:
                    logger.info(f"New domain inserted: {domain}")
                    await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="domain", result=domain)
    
    async def process_url(self, msg: Dict[str, Any]):
        if msg:
            logger.info(msg)
            msg_data = msg.get('data', {})
            # Extract hostname from the URL
            for d in msg_data:
                try:
                    parsed_url = urlparse(d.get('url'))
                    hostname = parsed_url.hostname
                    if not hostname:
                        logger.error(f"Failed to extract hostname from URL: {d.get('url')}")
                        return
                    #program_name = await self.db_manager.get_program_name(msg.get('program_id'))
                    #logger.info(await self.db_manager.get_programs())
                    # Check if the hostname matches the scope regex
                    is_in_scope = await self.db_manager.check_domain_regex_match(hostname, msg.get('program_id'))
                    if not is_in_scope:
                        #logger.info(f"Hostname {hostname} is not in scope for program {program_name}. Skipping.")
                        return
                    logger.info(f"Processing URL result for program {msg.get('program_id')}: {d.get('url', {})}")
                    result = await self.db_manager.insert_url(
                        url=d.get('url'),
                        httpx_data=d.get('httpx_data', {}),
                        program_id=msg.get('program_id')
                    )
                    logger.debug(result)
                    # Send a job to the workers to test the URL if httpx_data is missing
                    if not d.get('httpx_data'):
                        logger.info(f"Sending job to test URL: {d.get('url')}")
                        await self.qm.publish_message(subject="function.execute", stream="FUNCTION_EXECUTE", message={"function": "test_http", "program_id": msg.get('program_id'), "params": {"target": d.get('url')}})
            
                except Exception as e:
                    logger.error(f"Failed to process URL in program {msg.get('program_id')}: {e}")
                    logger.exception(e)
    
    async def process_nuclei(self, msg: Dict[str, Any]):
        if msg:
            logger.debug(f"Processing Nuclei result for program {msg.get('program_id')}: {msg}")
            msg_data = msg.get('data', {})
            for d in msg_data:
                try:
                    if d.get("type", "") == 'http':
                        parsed_url = urlparse(d.get('url', ""))
                        hostname = parsed_url.hostname
                    else:
                        hostname = d.get('url', "").split(":")[0]
                    if not hostname:
                        logger.error(f"Failed to extract hostname from URL: {d.get('output', {}).get('http', {}).get('url', {})}")
                        continue
                    else:
                        is_in_scope = await self.db_manager.check_domain_regex_match(hostname, msg.get('program_id'))
                        if is_in_scope:
                            logger.info(f"Processing Nuclei result for program {msg.get('program_id')}: {d.get('matched_at', {})}")
                            inserted = await self.db_manager.insert_nuclei(
                                program_id=msg.get('program_id'),
                                data=d
                            )
                            if inserted:
                                logger.info(f"New Nuclei result inserted: {d.get('matched_at', {})} | {d.get('template_id', {})} | {d.get('severity', {})}")
                        else:
                            logger.info(f"Hostname {hostname} is not in scope for program {msg.get('program_id')}. Skipping.")
                except Exception as e:
                    logger.error(f"Failed to process Nuclei result in program {msg.get('program_id')}: {e}")
                    logger.exception(e)

    async def process_service(self, msg_data: Dict[str, Any]):
        #logger.info(msg_data)
        if not isinstance(msg_data.get('data'), list):
            msg_data['data'] = [msg_data.get('data')]
        for i in msg_data.get('data'):
            inserted = await self.db_manager.insert_service(ip=i.get("ip"), port=i.get("port"), protocol=i.get("protocol"), program_id=msg_data.get('program_id'), service=i.get("service"))
            #if inserted:
            #    await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="ip", result=ip)

    async def process_certificate(self, msg: Dict[str, Any]):
        if msg:
            logger.debug(f"Processing certificate for program {msg.get('program_id')}: {msg}")
            msg_data = msg.get('data', {})
            for d in msg_data:
                try:
                    logger.info(f"Processing certificate for program {msg.get('program_id')}: {d.get('subject_cn', {})}")
                    inserted = await self.db_manager.insert_certificate(
                        program_id=msg.get('program_id'),
                        data=d
                    )
                    if inserted:
                        logger.info(f"New certificate inserted: {d.get('cert', {}).get('serial', {})}")
                    else:
                        logger.info(f"Certificate updated: {d.get('cert', {}).get('serial', {})}")
                except Exception as e:
                    logger.error(f"Failed to process certificate in program {msg.get('program_id')}: {e}")
                    logger.exception(e)

    async def process_service(self, msg_data: Dict[str, Any]):
        #logger.info(msg_data)
        if not isinstance(msg_data.get('data'), list):
            msg_data['data'] = [msg_data.get('data')]
        for i in msg_data.get('data'):
            inserted = await self.db_manager.insert_service(ip=i.get("ip"), port=i.get("port"), protocol=i.get("protocol"), program_id=msg_data.get('program_id'), service=i.get("service"))
            #if inserted:
            #    await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="ip", result=ip)

    async def _health_check(self):
        """Monitor processor health and subscription status."""
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                if self._last_message_time:
                    time_since_last_message = current_time - self._last_message_time
                    if time_since_last_message > timedelta(minutes=5):
                        logger.warning(f"No messages received for {time_since_last_message}. Reconnecting subscriptions...")
                        await self._reconnect_subscriptions()
                
                # Check if we're still connected to NATS
                if not self.qm.nc.is_connected:
                    logger.error("NATS connection lost. Attempting to reconnect...")
                    await self.qm.ensure_connected()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                await asyncio.sleep(5)

    async def _reconnect_subscriptions(self):
        """Reconnect all subscriptions."""
        try:
            logger.info("Reconnecting subscriptions...")
            await self.qm.connect()
            self.data_subscription = await self._setup_subscription(
                subject="recon.data",
                stream="RECON_DATA",
                message_handler=self.message_handler,
                queue_group="dataprocessor"
            )
            logger.info("Successfully reconnected subscriptions")
        except Exception as e:
            logger.error(f"Error reconnecting subscriptions: {e}")

    async def control_message_handler(self, raw_msg):
        """Handle control messages for pausing/unpausing the processor"""
        try:
            msg = json.loads(raw_msg.data.decode())
            command = msg.get("command")
            target = msg.get("target", "all")
            target_id = msg.get("target_id")

            # Check if message is targeted for this processor
            if target not in ["all", "dataprocessor"] and target != self.dataprocessor_id:
                logger.debug(f"Ignoring control message - not for this processor (target: {target})")
                return
            
            # For processor-specific targeting, check if this is the intended processor
            if target == "dataprocessor" and target_id and target_id != self.dataprocessor_id:
                logger.debug(f"Ignoring processor-specific message - not for this processor ID (target_id: {target_id})")
                return

            if command == "pause":
                logger.debug(f"Received pause command for {target} {target_id or ''}")
                if self.state == ProcessorState.PAUSED:
                    logger.debug("Data processor is already paused, skipping pause command")
                
                self.state = ProcessorState.PAUSED
                self.running.clear()  # Pause message processing
                
                # Unsubscribe from data subscription
                if self.data_subscription:
                    try:
                        await self.data_subscription.unsubscribe()
                        logger.debug(f"Unsubscribed from data subscription: {self.data_subscription}")
                        self.data_subscription = None
                    except Exception as e:
                        logger.error(f"Error unsubscribing: {e}")
                
                logger.info(f"Data processor {self.dataprocessor_id} paused")
                
                # Send acknowledgment
                await self.qm.publish_message(
                    subject="function.control.response",
                    stream="FUNCTION_CONTROL_RESPONSE",
                    message={
                        "processor_id": self.dataprocessor_id,
                        "type": "dataprocessor",
                        "status": "paused",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            
            elif command == "unpause":
                logger.debug("Received unpause command")
                self.state = ProcessorState.RUNNING
                self.running.set()  # Resume message processing
                
                # Resubscribe to the data stream
                self.data_subscription = await self._setup_subscription(
                    subject="recon.data",
                    stream="RECON_DATA",
                    message_handler=self.message_handler,
                    queue_group="dataprocessor"
                )
                logger.debug(f"Resubscribed to data subscription: {self.data_subscription}")
                
                logger.info(f"Data processor {self.dataprocessor_id} resumed")
                
                # Send acknowledgment
                await self.qm.publish_message(
                    subject="function.control.response",
                    stream="FUNCTION_CONTROL_RESPONSE",
                    message={
                        "processor_id": self.dataprocessor_id,
                        "type": "dataprocessor",
                        "status": "running",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )

            elif command == "report":
                logger.info("Received report command")
                report = await self.generate_report()
                logger.debug(f"Report: {report}")
                # Send report through control response channel
                await self.qm.publish_message(
                    subject="function.control.response",
                    stream="FUNCTION_CONTROL_RESPONSE",
                    message={
                        "processor_id": self.dataprocessor_id,
                        "type": "dataprocessor",
                        "command": "report",
                        "report": report,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                logger.debug("Data processor report sent")
            await raw_msg.ack()
        except Exception as e:
            logger.error(f"Error handling control message: {e}")
            await raw_msg.nak()
    async def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive report of the data processor's current state."""
        try:
            # Get process info
            process = psutil.Process()
            cpu_percent = process.cpu_percent(interval=1)
            mem_info = process.memory_info()
            
            report = {
                "processor": {
                    "id": self.dataprocessor_id,
                    "version": __version__,
                    "hostname": socket.gethostname(),
                    "state": self.state.value,
                    "uptime": (datetime.now(timezone.utc) - self._start_time).total_seconds() if hasattr(self, '_start_time') else None,
                    "last_message_time": self._last_message_time.isoformat() if self._last_message_time else None
                },
                "system": {
                    "platform": platform.platform(),
                    "python_version": sys.version,
                    "cpu_count": psutil.cpu_count(),
                    "total_memory": psutil.virtual_memory().total
                },
                "process": {
                    "cpu_percent": cpu_percent,
                    "memory_usage": {
                        "rss": mem_info.rss,  # Resident Set Size
                        "vms": mem_info.vms,  # Virtual Memory Size
                        "percent": process.memory_percent()
                    },
                    "threads": process.num_threads()
                },
                "queues": {
                    "nats_connected": self.qm.nc.is_connected if self.qm else False,
                    "data_subscription": {
                        "active": self.data_subscription is not None,
                        "queue_group": "dataprocessor"
                    },
                    "control_subscription": {
                        "active": self.control_subscription is not None
                    }
                },
                "processors": {
                    "registered_types": list(self.data_type_processors.keys())
                }
            }
            
            return report
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return {"error": str(e)}

async def main():
    config = Config()
    config.setup_logging()
    data_processor = DataProcessor(config)
    await data_processor.start()
    
    try:
        # Keep the data processor running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await data_processor.stop()

def run():
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())