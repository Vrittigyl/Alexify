"""
services/logging_config.py — Structured JSON Logging
=====================================================
Phase 1 addition.

Replaces plain-text basicConfig with a JSON formatter so every log line is
parseable by CloudWatch Logs Insights, Kibana, or any structured log aggregator.

Fields emitted per record:
  timestamp   – ISO-8601 UTC
  level       – DEBUG / INFO / WARNING / ERROR / CRITICAL
  service     – logger name (e.g. 'saathi.rte', 'saathi.rule_engine')
  message     – the log message
  request_id  – correlation ID (if present on the record)
  household_id – household context (if present)
  event_id    – event being processed (if present)
  exc_info    – exception traceback (if present)

Usage:
    from services.logging_config import configure_logging
    configure_logging()   # call once, at application startup

Adding context to log records (ContextFilter automatically reads contextvars):
    from services.logging_config import request_id_var, household_id_var, event_id_var
    request_id_var.set("req-abc123")
"""

import json
import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone

# ── Context variables propagated through the async call chain ──
# Set these at request ingestion time; all loggers in the same
# coroutine will automatically include them in every JSON record.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
household_id_var: ContextVar[str] = ContextVar("household_id", default="")
event_id_var: ContextVar[str] = ContextVar("event_id", default="")


class _ContextFilter(logging.Filter):
    """Injects context-var values into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        record.household_id = household_id_var.get("")
        record.event_id = event_id_var.get("")
        return True


class _JsonFormatter(logging.Formatter):
    """Formats each LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": record.name,
            "message": record.getMessage(),
        }

        # Optional contextual fields — only emit when non-empty
        for field in ("request_id", "household_id", "event_id"):
            val = getattr(record, field, "")
            if val:
                obj[field] = val

        if record.exc_info:
            obj["exc_info"] = "".join(traceback.format_exception(*record.exc_info))

        return json.dumps(obj, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure root logger with JSON formatter and context filter.
    Call exactly once at application startup (main.py lifespan or top-level).
    Safe to call multiple times — idempotent via handler-count check.
    """
    root = logging.getLogger()

    # Idempotency guard: don't add duplicate handlers
    if any(isinstance(h, logging.StreamHandler) and isinstance(getattr(h, "formatter", None), _JsonFormatter)
           for h in root.handlers):
        return

    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)

    # Suppress overly verbose third-party loggers
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
