from h3xrecon.core.worker import Worker, WorkerState
from h3xrecon.core import Config
from h3xrecon.core.queue import StreamUnavailableError
from h3xrecon.core.utils import check_last_execution, parse_url, is_valid_url, get_domain_from_url
from h3xrecon.plugins import ReconPlugin
from nats.js.api import AckPolicy, DeliverPolicy, ReplayPolicy
from dataclasses import dataclass
from typing import Dict, Any, List, Callable, Optional
from loguru import logger
from urllib.parse import urlparse 
import os
import json
import asyncio
import importlib
import pkgutil
import sys
import urllib.parse
import hashlib
from datetime import datetime, timezone, timedelta

@dataclass
class JobConfig:
    function_name: str
    param_map: Callable[[Any], Dict[str, Any]]

# Job mapping configuration
JOB_MAPPING: Dict[str, List[JobConfig]] = {
    "domain": [
       JobConfig(function_name="test_domain_catchall", param_map=lambda result: {"target": result.lower()}),
       JobConfig(function_name="resolve_domain", param_map=lambda result: {"target": result.lower()}),
       JobConfig(function_name="test_http", param_map=lambda result: {"target": result.lower()}),
       JobConfig(function_name="nuclei", param_map=lambda result: {"target": result.lower(), "extra_params": ["-as"]}),
    ],
    "ip": [
       JobConfig(function_name="reverse_resolve_ip", param_map=lambda result: {"target": result.lower()}),
       JobConfig(function_name="port_scan", param_map=lambda result: {"target": result.lower()})
    ],
    "website": [
       JobConfig(function_name="screenshot", param_map=lambda result: {"target": result.lower()}),
       JobConfig(function_name="test_http", param_map=lambda result: {"target": result.lower()}),
       JobConfig(function_name="nuclei", param_map=lambda result: {"target": result.lower(), "extra_params": ["-as"]}),
    ]
}

class DataWorker(Worker):
    def __init__(self, config: Config = Config()):
        super().__init__("data", config)
        self.trigger_threshold = timedelta(hours=24)
        self.plugins: Dict[str, Callable] = {}
        self.load_plugins()
        self.data_type_processors = {
            "ip": self.process_ip,
            "domain": self.process_domain,
            "service": self.process_service,
            "nuclei": self.process_nuclei,
            "certificate": self.process_certificate,
            "screenshot": self.process_screenshot,
            "website": self.process_website,
            "website_path": self.process_website_path
        }
        self.current_task: Optional[asyncio.Task] = None

    async def setup_subscriptions(self):
        """Setup NATS subscriptions for the data processor."""
        try:
            async with self._subscription_lock:
                if self.state == WorkerState.PAUSED:
                    logger.debug("Data processor is paused, skipping subscription setup")
                    return

                # Clean up existing subscriptions using parent class method
                await self._cleanup_subscriptions()

                subscription = await self.qm.subscribe(
                    subject="data.input",
                    stream="DATA_INPUT",
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
                self._sub_key = "DATA_INPUT:data.input:DATA_WORKERS"
                logger.debug(f"Subscribed to data channel: {self._sub_key}")

                # Setup control subscriptions
                await self.qm.subscribe(
                    subject="worker.control.all",
                    stream="WORKER_CONTROL",
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
                    subject="worker.control.all_data",
                    stream="WORKER_CONTROL",
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
                    subject=f"worker.control.{self.component_id}",
                    stream="WORKER_CONTROL",
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
    
    def load_plugins(self):
        """Dynamically load all recon plugins."""
        try:
            package = importlib.import_module('h3xrecon.plugins.plugins')
            logger.debug(f"Found plugin package at: {package.__path__}")
            
            # Walk through all subdirectories
            plugin_modules = []
            for finder, name, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
                if not name.endswith('.base'):  # Skip the base module
                    plugin_modules.append(name)
            
            logger.info(f"LOADED PLUGINS: {', '.join(p.split('.')[-1] for p in plugin_modules)}")
            
        except ModuleNotFoundError as e:
            logger.error(f"Failed to import 'plugins': {e}")
            return

        for module_name in plugin_modules:
            try:
                logger.debug(f"Attempting to load module: {module_name}")
                module = importlib.import_module(module_name)
                
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    
                    if not isinstance(attribute, type) or not issubclass(attribute, ReconPlugin) or attribute is ReconPlugin:
                       continue
                        
                    plugin_instance = attribute()
                    self.plugins[plugin_instance.name] = {
                        'plugin': plugin_instance,
                        'format_input': plugin_instance.format_input,
                        'is_valid_input': plugin_instance.is_valid_input
                    }
                    logger.debug(f"Loaded plugin: {plugin_instance.name}")
                
            except Exception as e:
                logger.error(f"Error loading plugin '{module_name}': {e}", exc_info=True)
        logger.debug(f"Current plugins list: {[key for key in self.plugins.keys()]}")
    
    async def _process_data(self, msg, processor, raw_msg):
        """Internal method to process data with the appropriate processor."""
        try:
            await self.set_state(WorkerState.BUSY, f"processing:{msg.get('data_type')}")
            await processor(msg)
            await raw_msg.ack()
        except Exception as e:
            logger.error(f"Error processing message: {e}")
        finally:
            if not raw_msg._ackd:
                await raw_msg.ack()
            await self.set_state(WorkerState.IDLE)

    async def message_handler(self, raw_msg):
        """Handle incoming data messages."""
        msg = json.loads(raw_msg.data.decode())
        if self.state == WorkerState.PAUSED:
            logger.debug("Data processor is paused, skipping message processing")
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
                # Create a cancellable task for data processing
                self.current_task = asyncio.create_task(
                    self._process_data(msg, processor, raw_msg)
                )
                await self.current_task
            else:
                logger.error(f"No processor found for data type: {msg.get('data_type')}")
                await raw_msg.nak()
                return
        except asyncio.CancelledError:
            logger.warning(f"DATA PROCESSING CANCELLED: {msg.get('data_type')} : {msg.get('data')}")
            if not raw_msg._ackd:
                await raw_msg.nak()
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            if not raw_msg._ackd:
                await raw_msg.ack()

    async def trigger_new_jobs(self, program_id: int, data_type: str, result: Any):
        """Trigger new jobs based on processed data."""
        # Check if processor is paused before triggering new jobs
        if self.state == WorkerState.PAUSED:
            logger.info("JOB TRIGGERING DISABLED: data worker is paused")
            return

        if os.getenv("H3XRECON_NO_NEW_JOBS", "false").lower() == "true":
            logger.info("JOB TRIGGERING DISABLED: H3XRECON_NO_NEW_JOBS is set")
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
            # TODO: Parse urls and check if host is in scope
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
                        "function_name": job.function_name,
                        "program_id": program_id,
                        "params": job.param_map(result)
                    }
                    new_job['params'] = await self.plugins[job.function_name]['format_input'](new_job['params'])

                    if await self._should_trigger_job(job.function_name, new_job.get('params', {})):
                        try:
                            logger.info(f"JOB TRIGGERED: {job.function_name}")
                            await self.qm.publish_message(
                                subject="recon.input",
                                stream="RECON_INPUT",
                                message=new_job
                            )
                            triggered_jobs.append(job.function_name)
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
                    else:
                        logger.debug(f"Job {job.function_name} not triggered for {result}: already executed recently")

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
        if self.state == WorkerState.PAUSED:
            logger.debug("Data processor is paused, skipping delayed job trigger")
            return

        await asyncio.sleep(5)
        job = JOB_MAPPING[data_type][next_job_index]
        new_job = {
            "function_name": job.function_name,
            "program_id": program_id,
            "params": job.param_map(result)
        }
        logger.debug(f"New job: {new_job}")
        if await self._should_trigger_job(new_job.get('function_name'), new_job.get('params', {})):
            await self.qm.publish_message(subject="recon.input", stream="RECON_INPUT", message=new_job)
        else:
            logger.debug(f"Job {job.function_name} not triggered for {result}: already executed recently")
        
        # Schedule next job if there are more
        if next_job_index < len(JOB_MAPPING[data_type]) - 1:
            logger.debug("scheduling next job trigger in 10 seconds")
            asyncio.create_task(self._delay_next_job(program_id, data_type, result, next_job_index + 1))
    
    async def _should_trigger_job(self, function_name: str, params: Dict[str, Any]) -> bool:
        """
        Check if a function should be executed based on its last execution time.
        Returns True if the function should be executed, False otherwise.
        """
        try:
            time_since_last = check_last_execution(function_name, params, self.redis_cache)
            return time_since_last > self.trigger_threshold if time_since_last else True

        except Exception as e:
            logger.error(f"Error checking execution history: {e}")
            # If there's an error checking history, allow execution
            return True
    
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
            if is_valid_url(domain):
                logger.warning(f"Domain {domain} is a URL, extracting domain")
                domain = get_domain_from_url(domain)
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
                if result.success:
                    if result.data.get('inserted'):
                        logger.success(f"INSERTED DOMAIN: {domain}")
                        await self.trigger_new_jobs(program_id=msg_data.get('program_id'), data_type="domain", result=domain)
                    else:
                        logger.info(f"UPDATED DOMAIN: {domain}")
                else:
                    logger.error(f"Failed to insert or update domain: {result.error}")
    
    async def process_website(self, msg: Dict[str, Any]):
        """Process website data."""
        if msg:
            msg_data = msg.get('data', {})
            # Extract hostname from the URL
            for d in msg_data:
                try:
                    url = d.get('url')
                    parsed_url = urlparse(url)
                    hostname = parsed_url.hostname
                    if not hostname:
                        logger.error(f"Failed to extract hostname from URL: {d.get('url')}")
                        return
                    # Check if the hostname matches the scope regex
                    is_in_scope = await self.db.check_domain_regex_match(hostname, msg.get('program_id'))
                    if not is_in_scope:
                        return
                    
                    if not parsed_url.port:
                        if parsed_url.scheme == 'https':
                            url = f"{url}:443"
                        elif parsed_url.scheme == 'http': 
                            url = f"{url}:80"
                    parsed_url = urllib.parse.urlparse(url)
                    logger.info(f"PROCESSING WEBSITE: {url}")
                    logger.debug(f"Data: {d}")
                    result = await self.db.insert_website(
                        url=url,
                        host=parsed_url.hostname,
                        port=parsed_url.port,
                        scheme=parsed_url.scheme,
                        techs=d.get('techs', []),
                        favicon_hash=d.get('favicon_hash', ""),
                        favicon_url=d.get('favicon_url', ""),
                        program_id=msg.get('program_id')
                    )
                    if result.success:
                        if result.data.get('inserted'):
                            logger.success(f"INSERTED WEBSITE: {url}")
                            await self.trigger_new_jobs(program_id=msg.get('program_id'), data_type="website", result=url)
                        else:
                            logger.info(f"UPDATED WEBSITE: {url}")
                    else:
                        logger.error(f"Failed to insert or update website: {result.error}")

                except Exception as e:
                    logger.error(f"Failed to process website in program {msg.get('program_id')}: {e}")
                    logger.exception(e)
    
    async def process_website_path(self, msg: Dict[str, Any]):
        """Process website path data."""
        if msg:
            msg_data = msg.get('data', {})
            # Extract hostname from the URL
            for d in msg_data:
                try:
                    _url = d.get('url')
                    parsed_website_and_path = parse_url(_url)
                    base_url = parsed_website_and_path.get('website', {}).get('url')
                    full_url = parsed_website_and_path.get('website_path', {}).get('url')
                    parsed_url = urlparse(full_url)
                    website_id = await self.db._fetch_value(f"SELECT id FROM websites WHERE url = '{base_url}'")
                    logger.info(f"PROCESSING WEBSITE PATH: {d.get('url')}")
                    result = await self.db.insert_website_path(
                        program_id=msg.get('program_id'),
                        website_id=website_id.data if website_id.data else 0,
                        path=parsed_url.path if parsed_url.path else "/",
                        final_path=d.get('final_url'),
                        techs=d.get('techs', []),
                        response_time=d.get('response_time'),
                        lines=d.get('lines'),
                        title=d.get('title'),
                        words=d.get('words'),
                        method=d.get('method'),
                        scheme=d.get('scheme'),
                        status_code=d.get('status_code'),
                        content_type=d.get('content_type'),
                        content_length=d.get('content_length'),
                        chain_status_codes=d.get('chain_status_codes'),
                        page_type=d.get('page_type'),
                        body_preview=d.get('body_preview'),
                        resp_header_hash=d.get('resp_header_hash'),
                        resp_body_hash=d.get('resp_body_hash')
                    )
                    if result.success:
                        if result.data.get('inserted'):
                            logger.success(f"INSERTED WEBSITE PATH: {d.get('url')}")
                        else:
                            logger.info(f"UPDATED WEBSITE PATH: {d.get('url')}")
                    else:
                        logger.error(f"Failed to insert or update website path: {result.error}")

                except Exception as e:
                    logger.error(f"Failed to process website path in program {msg.get('program_id')}: {e}")
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
                            result = await self.db.insert_nuclei(
                                program_id=msg.get('program_id'),
                                data=d
                            )
                            if result.success:
                                if result.data.get('inserted') is True:
                                    logger.success(f"INSERTED NUCLEI: {d.get('matched_at', {})} | {d.get('template_id', {})} | {d.get('severity', {})}")
                                else:
                                    logger.info(f"UPDATED NUCLEI: {d.get('matched_at', {})} | {d.get('template_id', {})} | {d.get('severity', {})}")
                            else:
                                logger.error(f"Failed to insert or update Nuclei hit: {result.error}")
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
                    result = await self.db.insert_certificate(
                        program_id=msg.get('program_id'),
                        data=d
                    )
                    if result.success:
                        if result.data.get('inserted'):
                            logger.success(f"INSERTED CERTIFICATE: {d.get('cert', {}).get('serial', {})}")
                        else:
                            logger.info(f"UPDATED CERTIFICATE: {d.get('cert', {}).get('serial', {})}")
                    else:
                        logger.error(f"Failed to insert or update certificate: {result.error}")
                except Exception as e:
                    logger.error(f"Failed to process certificate in program {msg.get('program_id')}: {e}")
                    logger.exception(e)

    async def process_service(self, msg_data: Dict[str, Any]):
        """Process service data."""
        if not isinstance(msg_data.get('data'), list):
            msg_data['data'] = [msg_data.get('data')]
        for i in msg_data.get('data'):
            logger.info(f"PROCESSING SERVICE: {i.get('ip')}:{i.get('port')}/{i.get('protocol')}/{i.get('service')}")
            result = await self.db.insert_service(
                ip=i.get("ip"), 
                port=i.get("port"), 
                protocol=i.get("protocol"), 
                program_id=msg_data.get('program_id'), 
                service=i.get("service")
            )
            if result.success:
                if result.data.get('inserted'):
                    logger.success(f"INSERTED SERVICE: {i.get('ip')}:{i.get('port')}/{i.get('protocol')}/{i.get('service')}")
                else:
                    logger.info(f"UPDATED SERVICE: {i.get('ip')}:{i.get('port')}/{i.get('protocol')}/{i.get('service')}")
            else:
                logger.error(f"Failed to insert or update service: {result.error}")
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