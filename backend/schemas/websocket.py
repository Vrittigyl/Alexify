from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

class WSEventType(str, Enum):
    """Supported WebSocket event types."""
    EVENT_INGESTED = "event_ingested"
    RTE_DECISION = "rte_decision"
    RULE_ENGINE_RESULT = "rule_engine_result"
    BEDROCK_REQUEST = "bedrock_request"
    BEDROCK_RESPONSE = "bedrock_response"
    ACTION_PLANNED = "action_planned"
    ACTION_PLANNER_STEP = "action_planner_step"
    COMMAND_DISPATCHED = "command_dispatched"
    NOTIFICATION_SENT = "notification_sent"
    CIRCUIT_BREAKER_STATE = "circuit_breaker_state"
    METRICS_UPDATE = "metrics_update"
    PATTERN_UPDATE = "pattern_update"

class WSMessage(BaseModel):
    """WebSocket message payload."""
    type: WSEventType
    household_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict)
