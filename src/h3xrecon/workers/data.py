from h3xrecon.core.component import ReconComponent, ProcessorState
from h3xrecon.core import Config
from h3xrecon.core.queue import StreamUnavailableError
from h3xrecon.__about__ import __version__
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from dataclasses import dataclass
from typing import Dict, Any, List, Callable
from loguru import logger
from urllib.parse import urlparse 
import os
import json
import asyncio
import sys
import hashlib
from datetime import datetime, timezone

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
    ],
    "ip": [
        JobConfig(function="reverse_resolve_ip", param_map=lambda result: {"target": result.lower()}),
        JobConfig(function="port_scan", param_map=lambda result: {"target": result.lower()})
    ],
    "url": [
        JobConfig(function="screenshot", param_map=lambda result: {"target": result.lower()})
    ]
}

class DataWorker(ReconComponent):
    def __init__(self, config: Config):
        super().__init__("data", config)
        self.data_type_processors = {
            "ip": self.process_ip,
            "domain": self.process_domain,
            "url": self.process_url,
            "service": self.process_service,
            "nuclei": self.process_nuclei,
            "certificate": self.process_certificate,
            "screenshot": self.process_screenshot
        }

    async def setup_subscriptions(self):
        """Setup NATS subscriptions for the data processor."""
        try:
            async with self._subscription_lock:
                if self.state == ProcessorState.PAUSED:
                    logger.debug("Data processor is paused, skipping subscription setup")
                    return

                # Clean up existing subscriptions using parent class method
                await self._cleanup_subscriptions()

                subscription = await self.qm.subscribe(
                    subject="recon.data",
                    stream="RECON_DATA",
                    durable_name="DATA_WORKERS",
                    message_handler=self.message_handler,
                    batch_size=1,
                    queue_group="dataworkers",
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.ALL,
                        'replay_policy': ReplayPolicy.INSTANT,
                        'max_deliver': 1,
                        'max_ack_pending': 1000,
                        'flow_control': False
                    },
                    pull_based=True
                )
                self._subscription = subscription
                self._sub_key = f"RECON_DATA:recon.data:DATA_WORKERS"
                logger.debug(f"Subscribed to data channel: {self._sub_key}")

                # Setup control subscriptions
                await self.qm.subscribe(
                    subject="function.control.all",
                    stream="FUNCTION_CONTROL",
                    durable_name=f"CONTROL_ALL_{self.component_id}",
                    message_handler=self.control_message_handler,
                    batch_size=1,
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT
                    },
                    broadcast=True
                )

                await self.qm.subscribe(
                    subject="function.control.all_data",
                    stream="FUNCTION_CONTROL",
                    durable_name=f"CONTROL_ALL_DATA_{self.component_id}",
                    message_handler=self.control_message_handler,
                    batch_size=1,
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT
                    },
                    broadcast=True
                )

                await self.qm.subscribe(
                    subject=f"function.control.{self.component_id}",
                    stream="FUNCTION_CONTROL",
                    durable_name=f"CONTROL_{self.component_id}",
                    message_handler=self.control_message_handler,
                    batch_size=1,
                    consumer_config={
                        'ack_policy': AckPolicy.EXPLICIT,
                        'deliver_policy': DeliverPolicy.NEW,
                        'replay_policy': ReplayPolicy.INSTANT
                    },
                    broadcast=True
                )

        except Exception as e:
            logger.error(f"Error setting up data processor subscriptions: {e}")
            raise

    async def message_handler(self, raw_msg):
        """Handle incoming data messages."""
        msg = json.loads(raw_msg.data.decode())
        if self.state == ProcessorState.PAUSED:
            await raw_msg.nak()
            return
        self._last_message_time = datetime.now(timezone.utc)
        logger.debug(f"Incoming message:\nObject Type: {type(msg)} : {json.dumps(msg)}")
        try:
            self.set_status("busy")
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
            logger.error(f"Error processing message: {e}")
        finally:
            if not raw_msg._ackd:
                await raw_msg.ack()
            await self.set_status("idle")

    async def trigger_new_jobs(self, program_id: int, data_type: str, result: Any):
        """Trigger new jobs based on processed data."""
        # Check if processor is paused before triggering new jobs
        if self.state == ProcessorState.PAUSED:
            return

        if os.getenv("H3XRECON_NO_NEW_JOBS", "false").lower() == "true":
            logger.debug("H3XRECON_NO_NEW_JOBS is set. Skipping triggering new jobs.")
            return

        try:
            await self.db.log_dataworker_operation(
                component_id=self.component_id,
                data_type=data_type,
                program_id=program_id,
                operation_type='trigger_job',
                data={'result': result},
                status='started'
            )

            # Check if the data is in the program scope, if it is a domain
            if data_type == "domain":
                is_in_scope = await self.db.check_domain_regex_match(result, program_id)
            else:
                is_in_scope = True
            if not is_in_scope:
                logger.debug(f"Data {result} of type {data_type} is not in scope for program {program_id}. Skipping new jobs.")
                await self.db.log_dataworker_operation(
                    component_id=self.component_id,
                    data_type=data_type,
                    program_id=program_id,
                    operation_type='trigger_job',
                    data={'result': result},
                    status='completed',
                    result={'skipped': True, 'reason': 'out_of_scope'},
                    completed_at=datetime.now(timezone.utc)
                )
                return

            triggered_jobs = []
            if data_type in JOB_MAPPING:
                for job in JOB_MAPPING[data_type]:
                    new_job = {
                        "function": job.function,
                        "program_id": program_id,
                        "params": job.param_map(result)
                    }
                    logger.info(f"JOB TRIGGERED: {job.function} : {result}")
                    try:
                        await self.qm.publish_message(
                            subject="function.execute",
                            stream="FUNCTION_EXECUTE",
                            message=new_job
                        )
                        triggered_jobs.append(job.function)
                    except StreamUnavailableError as e:
                        logger.error(f"Failed to trigger job - stream unavailable: {str(e)}")
                        await self.db.log_dataworker_operation(
                            component_id=self.component_id,
                            data_type=data_type,
                            program_id=program_id,
                            operation_type='trigger_job',
                            data={'result': result},
                            status='failed',
                            error_message=str(e),
                            completed_at=datetime.now(timezone.utc)
                        )
                        break
                    except Exception as e:
                        logger.error(f"Failed to trigger job: {str(e)}")
                        await self.db.log_dataworker_operation(
                            component_id=self.component_id,
                            data_type=data_type,
                            program_id=program_id,
                            operation_type='trigger_job',
                            data={'result': result},
                            status='failed',
                            error_message=str(e),
                            completed_at=datetime.now(timezone.utc)
                        )
                        raise

                    # Schedule next job if there are more
                    current_job_index = JOB_MAPPING[data_type].index(job)
                    if current_job_index < len(JOB_MAPPING[data_type]) - 1:
                        logger.debug("scheduling next job trigger in 10 seconds")
                        asyncio.create_task(self._delay_next_job(program_id, data_type, result, current_job_index + 1))
                        break

            # Log successful job triggers
            if triggered_jobs:
                await self.db.log_dataworker_operation(
                    component_id=self.component_id,
                    data_type=data_type,
                    program_id=program_id,
                    operation_type='trigger_job',
                    data={'result': result},
                    status='completed',
                    result={'triggered_jobs': triggered_jobs},
                    completed_at=datetime.now(timezone.utc)
                )

        except Exception as e:
            logger.error(f"Error triggering new jobs: {e}")
            await self.db.log_dataworker_operation(
                component_id=self.component_id,
                data_type=data_type,
                program_id=program_id,
                operation_type='trigger_job',
                data={'result': result},
                status='failed',
                error_message=str(e),
                completed_at=datetime.now(timezone.utc)
            )

    async def _delay_next_job(self, program_id: int, data_type: str, result: Any, next_job_index: int):
        """Helper method to handle delayed job triggering."""
        # Check state before proceeding with delayed job
        if self.state == ProcessorState.PAUSED:
            return

        await asyncio.sleep(5)
        job = JOB_MAPPING[data_type][next_job_index]
        new_job = {
            "function": job.function,
            "program_id": program_id,
            "params": job.param_map(result)
        }
        await self.qm.publish_message(subject="function.execute", stream="FUNCTION_EXECUTE", message=new_job)
        
        # Schedule next job if there are more
        if next_job_index < len(JOB_MAPPING[data_type]) - 1:
            logger.debug("scheduling next job trigger in 10 seconds")
            asyncio.create_task(self._delay_next_job(program_id, data_type, result, next_job_index + 1))

    ################################
    ## Data processing functions ##
    ################################

    async def process_ip(self, msg_data: Dict[str, Any]):
        """Process IP data."""
        if msg_data.get('attributes') is None:
            attributes = {}
        else:
            attributes = msg_data.get('attributes')
        for ip in msg_data.get('data'):
            try:
                await self.db.log_dataworker_operation(
                    component_id=self.component_id,
                    data_type='ip',
                    program_id=msg_data.get('program_id'),
                    operation_type='insert',
                    data={'ip': ip, 'attributes': attributes},
                    status='started'
                )

                ptr = attributes.get('ptr')
                if isinstance(ptr, list):
                    ptr = ptr[0] if ptr else None
                elif ptr == '':
                    ptr = None
                cloud_provider = attributes.get('cloud_provider', None)
                result = await self.db.insert_ip(ip=ip, ptr=ptr, cloud_provider=cloud_provider, program_id=msg_data.get('program_id'))
                
                # Log operation result
                if result.get('inserted'):
                    logger.success(f"INSERTED IP: {ip}")
                    await self.db.log_dataworker_operation(
                        component_id=self.component_id,
                        data_type='ip',
                        program_id=msg_data.get('program_id'),
                        operation_type='insert',
                        data={'ip': ip, 'attributes': attributes},
                        status='completed',
                        result={'inserted': True, 'id': result.get('id')},
                        completed_at=datetime.now(timezone.utc)
                    )
                    await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="ip", result=ip)
                else:
                    logger.info(f"UPDATED IP: {ip}")
            except Exception as e:
                await self.db.log_dataworker_operation(
                    component_id=self.component_id,
                    data_type='ip',
                    program_id=msg_data.get('program_id'),
                    operation_type='insert',
                    data={'ip': ip, 'attributes': attributes},
                    status='failed',
                    error_message=str(e),
                    completed_at=datetime.now(timezone.utc)
                )
                logger.error(f"Error processing IP {ip}: {e}")

    async def process_screenshot(self, msg_data: Dict[str, Any]):
        """Process screenshot data."""
        logger.debug(f"PROCESSING SCREENSHOT: {msg_data}")
        for screenshot in msg_data.get('data'):
            logger.info(f"PROCESSING SCREENSHOT: {screenshot}")
            md5_hash = hashlib.md5(open(screenshot.get('path'), 'rb').read()).hexdigest()
            result = await self.db.insert_screenshot(
                program_id=msg_data.get('program_id'),
                filepath=screenshot.get('path'),
                md5_hash=md5_hash,
                url=screenshot.get('url')
            )
            if result['inserted']:
                logger.success(f"INSERTED SCREENSHOT: {screenshot.get('url')}")
            else:
                logger.info(f"UPDATED SCREENSHOT: {screenshot.get('url')}")

    async def process_domain(self, msg_data: Dict[str, Any]):
        """Process domain data."""
        for domain in msg_data.get('data'):
            logger.info(f"PROCESSING DOMAIN: {domain}")
            if not await self.db.check_domain_regex_match(domain, msg_data.get('program_id')):
                logger.debug(f"Domain {domain} is not part of program {msg_data.get('program_id')}. Skipping processing.")
                continue
            else:
                # Get existing domain data first
                existing_domain = await self.db.get_domain(domain)
                
                # Get attributes with defaults from existing data
                if msg_data.get('attributes') is None:
                    attributes = {}
                else:
                    attributes = msg_data.get('attributes')
                
                # Only update is_catchall if explicitly provided
                is_catchall = attributes.get('is_catchall', existing_domain.get('is_catchall', False) if existing_domain else False)
                
                result = await self.db.insert_domain(
                    domain=domain, 
                    ips=attributes.get('ips', []), 
                    cnames=attributes.get('cnames', []), 
                    is_catchall=is_catchall,
                    program_id=msg_data.get('program_id')
                )
                if result.get('inserted'):
                    logger.success(f"INSERTED DOMAIN: {domain}")
                    await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="domain", result=domain)
                else:
                    logger.info(f"UPDATED DOMAIN: {domain}")
    
    async def process_url(self, msg: Dict[str, Any]):
        """Process URL data."""
        if msg:
            msg_data = msg.get('data', {})
            # Extract hostname from the URL
            for d in msg_data:
                try:
                    parsed_url = urlparse(d.get('url'))
                    hostname = parsed_url.hostname
                    if not hostname:
                        logger.error(f"Failed to extract hostname from URL: {d.get('url')}")
                        return
                    # Check if the hostname matches the scope regex
                    is_in_scope = await self.db.check_domain_regex_match(hostname, msg.get('program_id'))
                    if not is_in_scope:
                        return
                    logger.info(f"PROCESSING URL: {d.get('url', {})}")
                    result = await self.db.insert_url(
                        url=d.get('url'),
                        httpx_data=d.get('httpx_data', {}),
                        program_id=msg.get('program_id')
                    )
                    if result.get('inserted'):
                        logger.success(f"INSERTED URL: {d.get('url', {})}")
                    else:
                        logger.info(f"UPDATED URL: {d.get('url', {})}")
                        await self.trigger_new_jobs(program_id=msg.get('program_id'), data_type="url", result=d.get('url'))
                    # Send a job to the workers to test the URL if httpx_data is missing
                    if not d.get('httpx_data'):
                        logger.info(f"TRIGGERED JOB: test_http : {d.get('url')}")
                        await self.qm.publish_message(subject="function.execute", stream="FUNCTION_EXECUTE", message={"function": "test_http", "program_id": msg.get('program_id'), "params": {"target": d.get('url')}})
            
                except Exception as e:
                    logger.error(f"Failed to process URL in program {msg.get('program_id')}: {e}")
                    logger.exception(e)
    
    async def process_nuclei(self, msg: Dict[str, Any]):
        """Process Nuclei data."""
        if msg:
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
                        is_in_scope = await self.db.check_domain_regex_match(hostname, msg.get('program_id'))
                        if is_in_scope:
                            logger.info(f"PROCESSING NUCLEI: {d.get('matched_at', {})}")
                            inserted = await self.db.insert_nuclei(
                                program_id=msg.get('program_id'),
                                data=d
                            )
                            if inserted:
                                logger.success(f"INSERTED NUCLEI: {d.get('matched_at', {})} | {d.get('template_id', {})} | {d.get('severity', {})}")
                            else:
                                logger.info(f"UPDATED NUCLEI: {d.get('matched_at', {})} | {d.get('template_id', {})} | {d.get('severity', {})}")
                        else:
                            logger.debug(f"Hostname {hostname} is not in scope for program {msg.get('program_id')}. Skipping.")
                except Exception as e:
                    logger.error(f"Failed to process Nuclei result in program {msg.get('program_id')}: {e}")
                    logger.exception(e)

    async def process_certificate(self, msg: Dict[str, Any]):
        """Process certificate data."""
        if msg:
            logger.info(f"PROCESSING CERTIFICATE: {msg}")
            msg_data = msg.get('data', {})
            for d in msg_data:
                try:
                    inserted = await self.db.insert_certificate(
                        program_id=msg.get('program_id'),
                        data=d
                    )
                    if inserted:
                        logger.success(f"INSERTED CERTIFICATE: {d.get('cert', {}).get('serial', {})}")
                    else:
                        logger.info(f"UPDATED CERTIFICATE: {d.get('cert', {}).get('serial', {})}")
                except Exception as e:
                    logger.error(f"Failed to process certificate in program {msg.get('program_id')}: {e}")
                    logger.exception(e)

    async def process_service(self, msg_data: Dict[str, Any]):
        """Process service data."""
        if not isinstance(msg_data.get('data'), list):
            msg_data['data'] = [msg_data.get('data')]
        for i in msg_data.get('data'):
            logger.info(f"PROCESSING SERVICE: {i.get('ip')}:{i.get('port')}/{i.get('protocol')}/{i.get('service')}")
            inserted = await self.db.insert_service(
                ip=i.get("ip"), 
                port=i.get("port"), 
                protocol=i.get("protocol"), 
                program_id=msg_data.get('program_id'), 
                service=i.get("service")
            )
            if inserted:
                logger.success(f"INSERTED SERVICE: {i.get('ip')}:{i.get('port')}/{i.get('protocol')}/{i.get('service')}")
    async def _handle_killjob_command(self, msg: Dict[str, Any]):
        """Handle killjob command to cancel the running task."""
        pass
async def main():
    config = Config()
    config.setup_logging()

    data_processor = DataWorker(config)
    try:
        await data_processor.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await data_processor.stop()
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        sys.exit(1)

def run():
    asyncio.run(main())

if __name__ == "__main__":
    run()