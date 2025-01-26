from dataclasses import dataclass
from typing import Dict, Any, Optional
from loguru import logger
import uuid
from datetime import datetime
@dataclass
class ReconJobRequest:
    program_id: int
    function_name: str
    params: Dict[str, Any]
    force: bool = False
    execution_id: Optional[str] = None
    trigger_new_jobs: bool = True
    response_id: Optional[str] = None
    debug_id: Optional[str] = None

    def __post_init__(self):
        if self.execution_id is None:
            self.execution_id = str(uuid.uuid4())

@dataclass
class ReconJobOutput:
    execution_id: str
    timestamp: str
    program_id: int
    trigger_new_jobs: bool
    source: Dict[str, Any]
    data: Dict[str, Any]
    response_id: str
    def __post_init__(self):
        # Validate execution_id is a valid UUID
        try:
            uuid.UUID(self.execution_id)
        except ValueError:
            logger.error("execution_id must be a valid UUID")
            raise ValueError("execution_id must be a valid UUID")

        # Validate timestamp is a valid timestamp
        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError:
            logger.error("timestamp must be a valid ISO format timestamp")
            raise ValueError("timestamp must be a valid ISO format timestamp")

        # Validate program_id is an integer
        try:
            int(self.program_id)
        except ValueError:
            logger.error("program_id must be an integer")
            raise ValueError("program_id must be an integer")

        # Validate source is a dictionary
        if not isinstance(self.source, dict):
            logger.error("source must be a dictionary")
            raise TypeError("source must be a dictionary")

        # Validate output is a list
        if not isinstance(self.data, dict):
            logger.error("output must be a dictionary")
            raise TypeError("output must be a dictionary")
