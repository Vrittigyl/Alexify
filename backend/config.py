"""
config.py — SAATHI Central Configuration
=========================================
Single source of truth for all environment variables and system constants.
All modules import from here — never from os.environ directly.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── AWS ───────────────────────────────────────────────
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    aws_access_key_id: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")

    # ── Bedrock ───────────────────────────────────────────
    bedrock_mock_mode: bool = Field(default=True, alias="BEDROCK_MOCK_MODE")
    bedrock_model_id: str = Field(
        default="anthropic.claude-sonnet-4-5",
        alias="BEDROCK_MODEL_ID"
    )

    # ── Household ─────────────────────────────────────────
    household_id: str = Field(default="hh_xk92p_sharma", alias="HOUSEHOLD_ID")

    # ── RTE Thresholds ────────────────────────────────────
    bedrock_complexity_threshold: int = Field(
        default=40, alias="BEDROCK_COMPLEXITY_THRESHOLD"
    )
    bloom_window_secs: int = Field(default=60, alias="BLOOM_WINDOW_SECS")
    batcher_window_mins: int = Field(default=10, alias="BATCHER_WINDOW_MINS")
    batcher_max_batch_size: int = Field(default=15, alias="BATCHER_MAX_BATCH_SIZE")

    # ── Presence Service ──────────────────────────────────
    presence_ttl_secs: int = Field(default=300, alias="PRESENCE_TTL_SECS")

    # ── DynamoDB Table Names ──────────────────────────────
    table_household_graph: str = Field(
        default="HouseholdGraph", alias="DYNAMO_TABLE_HOUSEHOLD_GRAPH"
    )
    table_household_rules: str = Field(
        default="HouseholdRules", alias="DYNAMO_TABLE_HOUSEHOLD_RULES"
    )
    table_household_patterns: str = Field(
        default="HouseholdPatterns", alias="DYNAMO_TABLE_HOUSEHOLD_PATTERNS"
    )
    table_rte_audit_log: str = Field(
        default="RTEAuditLog", alias="DYNAMO_TABLE_RTE_AUDIT_LOG"
    )
    table_household_metrics: str = Field(
        default="HouseholdMetrics", alias="DYNAMO_TABLE_HOUSEHOLD_METRICS"
    )
    table_action_log: str = Field(
        default="ActionLog", alias="DYNAMO_TABLE_ACTION_LOG"
    )
    table_conflict_audit_log: str = Field(
        default="ConflictAuditLog", alias="DYNAMO_TABLE_CONFLICT_AUDIT_LOG"
    )

    # ── RTE Complexity Score Weights ──────────────────────
    # These are constants — never env vars
    RTE_SCORE_PER_MEMBER: int = 15
    RTE_SCORE_PER_LIFE_EVENT: int = 25
    RTE_SCORE_HEALTH_CONSTRAINT: int = 30
    RTE_SCORE_PER_CONFLICT: int = 20
    RTE_SCORE_MULTI_DEVICE: int = 15
    RTE_SCORE_AI_REQUIRED: int = 100   # always routes to Bedrock

    # ── Rule Engine ───────────────────────────────────────
    RULE_REGISTRY_REFRESH_SECS: int = 300        # refresh every 5 minutes
    IDEMPOTENCY_WINDOW_SECS: int = 300           # 5-minute idempotency window

    # ── Bedrock Circuit Breaker ───────────────────────────
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_WINDOW_SECS: int = 60
    CIRCUIT_BREAKER_PROBE_INTERVAL_SECS: int = 30

    # ── Notification ──────────────────────────────────────
    NOTIFICATION_RATE_LIMIT_COUNT: int = 3       # max per member per window
    NOTIFICATION_RATE_LIMIT_WINDOW_SECS: int = 600  # 10 minutes

    # ── Audit ─────────────────────────────────────────────
    RTE_AUDIT_TTL_DAYS: int = 90
    ACTION_LOG_TTL_DAYS: int = 30

    # ── AI Required Event Types (always route to Bedrock) ─
    AI_REQUIRED_EVENT_TYPES: list = [
        "life_event",
        "guest_arrival",
        "festival_declaration",
        "health_emergency",
    ]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton — import this everywhere
settings = Settings()
