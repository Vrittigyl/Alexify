import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator
from .enums import DeviceType, EventType, ImpactLevel

class NormalizedEvent(BaseModel):
    """
    Standard event schema.
    Adapters map raw device payloads to this format before processing.
    """
    # Identity
    event_id: str = Field(
        default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}",
        description="Unique event ID"
    )
    household_id: str = Field(..., description="Household ID")

    # Type classification
    event_type: EventType
    device_type: Optional[DeviceType] = None
    device_id: Optional[str] = None

    # Timing
    event_time: datetime = Field(default_factory=datetime.utcnow)
    received_time: datetime = Field(default_factory=datetime.utcnow)

    # Payload
    payload: dict[str, Any] = Field(default_factory=dict, description="Normalized device payload")

    # Metadata
    impact_level: ImpactLevel = Field(default=ImpactLevel.MEDIUM)
    dedup_key: Optional[str] = Field(default=None, description="Format: hh_id:dev_id:event_type:minute")
    adapter_id: Optional[str] = None
    room_id: Optional[str] = None
    affected_member_ids: list[str] = Field(default_factory=list)
    requires_ai: bool = Field(default=False, description="Forces routing to Bedrock if true")
    source_raw: Optional[dict[str, Any]] = Field(default=None, description="Original unparsed payload")

    @field_validator("impact_level", mode="before")
    @classmethod
    def coerce_impact_level(cls, v):
        if isinstance(v, str):
            return ImpactLevel(v.upper())
        return v
