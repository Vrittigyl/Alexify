"""
config.py — SAATHI Central Configuration
=========================================
Single source of truth for all environment variables and system constants.
All modules import from here — never from os.environ directly.

Phase 1 additions : API key auth, dev mode, CORS origins
Phase 2 additions : boto3 retry constants
Phase 3 additions : Redis connection
Phase 4 additions : SQS connection
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── AWS ───────────────────────────────────────────────
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    aws_access_key_id: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")

    # ── Security / Auth ───────────────────────────────────
    # dev_mode=True   → API key check skipped (safe for local dev & tests)
    # dev_mode=False  → X-API-Key header required on protected endpoints
    dev_mode: bool = Field(default=True, alias="DEV_MODE")
    api_key: str = Field(default="dev-saathi-key-change-in-prod", alias="SAATHI_API_KEY")

    # ── CORS ──────────────────────────────────────────────
    # Comma-separated list of allowed origins, read from env.
    # In dev_mode the wildcard is used automatically.
    allowed_origins_str: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="ALLOWED_ORIGINS",
    )

    @property
    def allowed_origins(self) -> list[str]:
        if self.dev_mode:
            return ["*"]
        return [o.strip() for o in self.allowed_origins_str.split(",") if o.strip()]

    # ── Redis ─────────────────────────────────────────────
    # redis_enabled=False → all services fall back to in-memory (default)
    # redis_enabled=True  → distributed state via ElastiCache / local Redis
    redis_enabled: bool = Field(default=False, alias="REDIS_ENABLED")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_socket_timeout: float = Field(default=1.0, alias="REDIS_SOCKET_TIMEOUT")
    redis_connect_timeout: float = Field(default=1.0, alias="REDIS_CONNECT_TIMEOUT")
    redis_health_check_interval: int = Field(default=30, alias="REDIS_HEALTH_CHECK_INTERVAL")

    # ── SQS ───────────────────────────────────────────────
    # sqs_enabled=False → events processed synchronously in-process (default)
    # sqs_enabled=True  → events enqueued in SQS, consumed by worker
    sqs_enabled: bool = Field(default=False, alias="SQS_ENABLED")
    sqs_queue_url: str = Field(default="", alias="SQS_QUEUE_URL")
    sqs_dlq_url: str = Field(default="", alias="SQS_DLQ_URL")
    sqs_visibility_timeout: int = Field(default=60, alias="SQS_VISIBILITY_TIMEOUT")

    # ── CloudWatch Metrics ────────────────────────────────
    cloudwatch_enabled: bool = Field(default=False, alias="CLOUDWATCH_ENABLED")
    cloudwatch_namespace: str = Field(default="SAATHI", alias="CLOUDWATCH_NAMESPACE")

    # ── boto3 Reliability ─────────────────────────────────
    DYNAMO_MAX_ATTEMPTS: int = 3          # exponential backoff retries
    DYNAMO_CONNECT_TIMEOUT: float = 5.0  # seconds
    DYNAMO_READ_TIMEOUT: float = 10.0    # seconds

    # ── Bedrock ───────────────────────────────────────────
    bedrock_mock_mode: bool = Field(default=True, alias="BEDROCK_MOCK_MODE")
    bedrock_model_id: str = Field(
        default="apac.amazon.nova-micro-v1:0",
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

    # ── Twilio ────────────────────────────────────────────
    # Set twilio_enabled=True + fill credentials to activate real dispatch.
    # TWILIO_FROM_WHATSAPP must be "whatsapp:+14155238886" (sandbox) or your approved number.
    # MEMBER_PHONE_MAP is a JSON object mapping member_id → E.164 phone number,
    # e.g. '{"mbr_papa_003": "+919876543210", "mbr_mama_001": "+919876543211"}'
    twilio_enabled: bool = Field(default=False, alias="TWILIO_ENABLED")
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_from_whatsapp: str = Field(default="whatsapp:+14155238886", alias="TWILIO_FROM_WHATSAPP")
    twilio_from_sms: str = Field(default="", alias="TWILIO_FROM_SMS")
    member_phone_map_json: str = Field(default="{}", alias="MEMBER_PHONE_MAP")

    @property
    def member_phone_map(self) -> dict[str, str]:
        import json
        try:
            return json.loads(self.member_phone_map_json)
        except Exception:
            return {}

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
