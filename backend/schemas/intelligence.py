from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from .enums import ConfidenceBand, DeviceType, EventType, RouteDecision

class MemberPresence(BaseModel):
    """Individual member presence state."""
    member_id: str
    room_id: Optional[str] = None
    detected_at: Optional[datetime] = None
    is_home: bool = True

class HouseholdContext(BaseModel):
    """
    Context snapshot used by the rule engine and Bedrock for decisions.
    """
    household_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    graph_cache_version: int = 0

    members_presence: list[MemberPresence] = Field(default_factory=list)

    # device_id mapping to state
    device_states: dict[str, dict[str, Any]] = Field(default_factory=dict)

    active_life_events: list[dict[str, Any]] = Field(default_factory=list)

    # Keeps track of the last few RTE decisions
    rte_routing_summary: list[dict[str, Any]] = Field(default_factory=list)

    time_of_day: Optional[str] = None
    ist_time: Optional[str] = None
    day_of_week: Optional[str] = None

class RTEDecision(BaseModel):
    """Routing decision logged to the audit table."""
    event_id: str
    household_id: str
    event_type: EventType
    device_type: Optional[DeviceType] = None

    route: RouteDecision
    stage_decided: int = Field(..., description="RTE stage that made the routing decision (1-4)")
    complexity_score: int = 0

    rule_matched: Optional[str] = None
    pattern_matched: Optional[str] = None

    score_breakdown: Optional[dict[str, int]] = None

    bedrock_tokens_used: Optional[int] = None

    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    audit_expiry: Optional[int] = None

class PatternRecord(BaseModel):
    """Tracked behavioral pattern."""
    household_id: str
    pattern_id: str
    description: Optional[str] = None

    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    observation_days: int = 0

    promoted_at: Optional[datetime] = None
    demoted_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    promoted_rule_id: Optional[str] = None

    # Track accuracy over time
    consecutive_misses: int = 0
    consecutive_overrides: int = 0
    total_observations: int = 0
    total_matches: int = 0

    member_id: Optional[str] = None
    device_type: Optional[DeviceType] = None
    device_id: Optional[str] = None
    event_type: Optional[EventType] = None
    time_window: Optional[str] = None
    day_pattern: Optional[list[str]] = None

    first_observed: Optional[datetime] = None
    last_observed: Optional[datetime] = None
    last_miss: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @staticmethod
    def compute_band(confidence: float, observation_days: int) -> ConfidenceBand:
        """Determines the confidence band based on score and observation time."""
        if confidence >= 0.90 and observation_days >= 30:
            return ConfidenceBand.PROMOTED
        elif confidence >= 0.60:
            return ConfidenceBand.LEARNING
        elif confidence >= 0.40:
            return ConfidenceBand.OBSERVING
        else:
            return ConfidenceBand.RETIRED
