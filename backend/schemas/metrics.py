from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .enums import CircuitState

class CircuitBreakerState(BaseModel):
    """Current state of the Bedrock circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_probe: Optional[datetime] = None
    window_start: Optional[datetime] = None
    consecutive_successes: int = 0

class DashboardMetrics(BaseModel):
    """
    Dashboard aggregation metrics for the frontend.
    """
    household_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Event routing totals
    total_events_processed: int = 0
    rule_engine_calls: int = 0
    bedrock_calls: int = 0
    suppressed_events: int = 0
    rule_engine_percentage: float = 0.0

    # Latency numbers
    avg_rule_engine_latency_ms: float = 0.0
    avg_bedrock_latency_ms: float = 0.0
    p99_rule_engine_latency_ms: float = 0.0

    # Token and cost tracking
    total_bedrock_tokens: int = 0
    avg_tokens_per_call: float = 0.0
    estimated_daily_cost_usd: float = 0.0

    # Architecture savings (v1 vs v2)
    v1_estimated_tokens_per_call: int = 3800
    v2_actual_tokens_per_call: float = 0.0
    token_savings_percentage: float = 0.0

    circuit_breaker: CircuitBreakerState = Field(default_factory=CircuitBreakerState)
    functionality_during_outage: float = 85.0

    # Pattern engine states
    active_patterns: int = 0
    promoted_patterns: int = 0
    learning_patterns: int = 0
    observing_patterns: int = 0

    # Action pipeline totals
    total_actions_dispatched: int = 0
    total_notifications_sent: int = 0
    actions_rate_limited: int = 0
    actions_conflict_resolved: int = 0
