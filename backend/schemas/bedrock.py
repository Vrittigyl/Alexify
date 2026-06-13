import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

class BedrockContext(BaseModel):
    """
    Context data passed to Bedrock. Includes only the targeted subgraph to save tokens.
    """
    household_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    graph_subgraph: dict[str, Any] = Field(default_factory=dict)
    active_life_events: list[dict[str, Any]] = Field(default_factory=list)
    members_presence: list[dict[str, Any]] = Field(default_factory=list)
    device_states: dict[str, Any] = Field(default_factory=dict)
    rule_engine_already_handled: list[str] = Field(default_factory=list)
    time_context: dict[str, str] = Field(default_factory=dict)
    estimated_tokens: Optional[int] = None

class BedrockResponse(BaseModel):
    """Response payload from Bedrock."""
    request_id: str = Field(
        default_factory=lambda: f"brk_{uuid.uuid4().hex[:12]}"
    )
    household_id: str

    actions: list[dict[str, Any]] = Field(default_factory=list)
    reasoning: Optional[str] = None
    confidence: float = 0.0

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    latency_ms: float = 0.0
    model_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Patterns suggested for future rule engine promotion
    suggested_patterns: list[dict[str, Any]] = Field(default_factory=list)
