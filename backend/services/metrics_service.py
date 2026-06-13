"""
metrics_service.py — Phase 9.8
================================
In-memory counters with async DynamoDB persistence (non-blocking).
Provides get_dashboard_metrics() that returns a fully populated DashboardMetrics.

Design:
  - All increments are O(1) dict updates — never block the hot path.
  - Latency tracking uses a fixed-size rolling window (100 samples).
  - DynamoDB writes are fire-and-forget (asyncio.create_task or asyncio.run).
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

from config import settings
from db.dynamo_client import get_table
from schemas.enums import CircuitState
from schemas.metrics import CircuitBreakerState, DashboardMetrics

logger = logging.getLogger(__name__)

_MAX_LATENCY_SAMPLES = 100


class MetricsService:
    """
    Singleton-safe in-memory metrics accumulator.
    One instance per household in production; shared singleton in demo mode.
    """

    def __init__(self, household_id: str):
        self._hh = household_id

        # Routing counters
        self._total = 0
        self._rule_engine = 0
        self._bedrock = 0
        self._suppressed = 0

        # Latency windows
        self._re_latencies: deque[float] = deque(maxlen=_MAX_LATENCY_SAMPLES)
        self._bk_latencies: deque[float] = deque(maxlen=_MAX_LATENCY_SAMPLES)

        # Token tracking
        self._total_tokens = 0
        self._bedrock_call_count = 0

        # Action pipeline
        self._actions_dispatched = 0
        self._notifications_sent = 0
        self._rate_limited = 0
        self._conflict_resolved = 0

        # Pattern tracking
        self._active_patterns = 0
        self._promoted_patterns = 0
        self._learning_patterns = 0
        self._observing_patterns = 0

        # Circuit breaker state (updated externally)
        self._circuit: CircuitBreakerState = CircuitBreakerState()

    # ── Increment APIs ───────────────────────────────────────

    def record_rule_engine(self, latency_ms: float = 0.0) -> None:
        self._total += 1
        self._rule_engine += 1
        self._re_latencies.append(latency_ms)
        self._async_persist()

    def record_bedrock(self, latency_ms: float = 0.0, tokens: int = 0) -> None:
        self._total += 1
        self._bedrock += 1
        self._bedrock_call_count += 1
        self._bk_latencies.append(latency_ms)
        self._total_tokens += tokens
        self._async_persist()

    def record_suppressed(self) -> None:
        self._total += 1
        self._suppressed += 1

    def record_action_dispatched(self) -> None:
        self._actions_dispatched += 1

    def record_notification_sent(self) -> None:
        self._notifications_sent += 1

    def record_rate_limited(self) -> None:
        self._rate_limited += 1

    def record_conflict_resolved(self) -> None:
        self._conflict_resolved += 1

    def update_circuit_breaker(self, state: CircuitState) -> None:
        self._circuit.state = state

    def update_pattern_counts(
        self,
        active: int = 0,
        promoted: int = 0,
        learning: int = 0,
        observing: int = 0,
    ) -> None:
        self._active_patterns = active
        self._promoted_patterns = promoted
        self._learning_patterns = learning
        self._observing_patterns = observing

    # ── Dashboard snapshot ───────────────────────────────────

    def get_dashboard_metrics(self) -> DashboardMetrics:
        re_pct = (self._rule_engine / self._total * 100) if self._total else 0.0
        avg_re = (sum(self._re_latencies) / len(self._re_latencies)) if self._re_latencies else 0.0
        p99_re = sorted(self._re_latencies)[int(len(self._re_latencies) * 0.99)] if self._re_latencies else 0.0
        avg_bk = (sum(self._bk_latencies) / len(self._bk_latencies)) if self._bk_latencies else 0.0
        avg_tokens = (self._total_tokens / self._bedrock_call_count) if self._bedrock_call_count else 0.0

        # Token savings: v1 sent ~3,800 tokens/call, v2 targets ~1,100-1,500
        v2_tokens = avg_tokens
        savings_pct = ((3800 - v2_tokens) / 3800 * 100) if v2_tokens > 0 else 0.0

        return DashboardMetrics(
            household_id=self._hh,
            total_events_processed=self._total,
            rule_engine_calls=self._rule_engine,
            bedrock_calls=self._bedrock,
            suppressed_events=self._suppressed,
            rule_engine_percentage=round(re_pct, 1),
            avg_rule_engine_latency_ms=round(avg_re, 2),
            avg_bedrock_latency_ms=round(avg_bk, 2),
            p99_rule_engine_latency_ms=round(p99_re, 2),
            total_bedrock_tokens=self._total_tokens,
            avg_tokens_per_call=round(avg_tokens, 1),
            estimated_daily_cost_usd=round(self._total_tokens * 0.000003, 4),
            v2_actual_tokens_per_call=round(v2_tokens, 1),
            token_savings_percentage=round(savings_pct, 1),
            circuit_breaker=self._circuit,
            active_patterns=self._active_patterns,
            promoted_patterns=self._promoted_patterns,
            learning_patterns=self._learning_patterns,
            observing_patterns=self._observing_patterns,
            total_actions_dispatched=self._actions_dispatched,
            total_notifications_sent=self._notifications_sent,
            actions_rate_limited=self._rate_limited,
            actions_conflict_resolved=self._conflict_resolved,
        )

    # ── Async persist ────────────────────────────────────────

    def _async_persist(self) -> None:
        """Fire-and-forget DynamoDB write. Never blocks the hot path."""
        try:
            from services.task_tracker import task_tracker
            task_tracker.spawn(self._write_to_dynamo, fallback="drop")
        except RuntimeError:
            # Not in async context (e.g., scripts/tests) — skip persist
            pass

    async def _write_to_dynamo(self) -> None:
        try:
            table = get_table("household_metrics")
            m = self.get_dashboard_metrics()
            item = {
                "household_id": m.household_id,
                "timestamp": m.timestamp.isoformat(),
                "total_events_processed": m.total_events_processed,
                "rule_engine_calls": m.rule_engine_calls,
                "bedrock_calls": m.bedrock_calls,
                "suppressed_events": m.suppressed_events,
                "rule_engine_percentage": Decimal(str(m.rule_engine_percentage)),
                "avg_rule_engine_latency_ms": Decimal(str(m.avg_rule_engine_latency_ms)),
                "avg_bedrock_latency_ms": Decimal(str(m.avg_bedrock_latency_ms)),
                "total_bedrock_tokens": m.total_bedrock_tokens,
                "avg_tokens_per_call": Decimal(str(m.avg_tokens_per_call)),
                "estimated_daily_cost_usd": Decimal(str(m.estimated_daily_cost_usd)),
                "token_savings_percentage": Decimal(str(m.token_savings_percentage)),
                "active_patterns": m.active_patterns,
                "promoted_patterns": m.promoted_patterns,
                "total_actions_dispatched": m.total_actions_dispatched,
                "total_notifications_sent": m.total_notifications_sent,
                "circuit_breaker_state": m.circuit_breaker.state.value,
            }
            table.put_item(Item=item)
        except Exception as e:
            logger.debug(f"MetricsService persist failed (non-critical): {e}")
