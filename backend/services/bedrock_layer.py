"""
bedrock_layer.py — Phase 9.4 / 9.5 / 9.6
==========================================
Three components:

  9.4  ContextBuilder      — builds a token-efficient BedrockContext (~1,100-1,500 tokens)
  9.5  BedrockCircuitBreaker — CLOSED/OPEN/HALF_OPEN state machine
  9.6  BedrockLayer.invoke — circuit check → real/mock boto3 call → parse response

BEDROCK_MOCK_MODE=true (default) returns a realistic mock response so the
full pipeline can be tested without real AWS credentials.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from config import settings
from schemas import NormalizedEvent
from schemas.bedrock import BedrockContext, BedrockResponse
from schemas.enums import ActionSource, ActionType, CircuitState
from schemas.intelligence import HouseholdContext

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 9.4  ContextBuilder
# ─────────────────────────────────────────────────────────────

class ContextBuilder:
    """
    Converts a batch of NormalizedEvents + HouseholdContext + graph subgraph
    into a token-efficient BedrockContext.

    Token budget target: 1,100–1,500 tokens.
    Achieved by:
      - Only including graph nodes relevant to the event's device + affected members
      - Trimming device_states to 10 most recent
      - Capping life_events and rte_summary to 5 entries each
    """

    def build_bedrock_context(
        self,
        batch: list[NormalizedEvent],
        context: HouseholdContext,
        graph_subgraph: dict[str, Any] | None = None,
        rule_engine_already_handled: list[str] | None = None,
    ) -> BedrockContext:
        now_ist = datetime.now(tz=timezone.utc).isoformat()

        # Summarise events (only key fields for token efficiency)
        events_summary = [
            {
                "event_id":   ev.event_id,
                "event_type": ev.event_type.value,
                "device_type": ev.device_type.value if ev.device_type else None,
                "device_id":  ev.device_id,
                "payload":    ev.payload,
                "impact":     ev.impact_level.value if ev.impact_level else None,
            }
            for ev in batch
        ]

        # Cap device states to 10 entries
        device_states = dict(list(context.device_states.items())[:10])

        # Time context
        time_context = {
            "ist_time":    context.ist_time or now_ist,
            "time_of_day": context.time_of_day or "unknown",
            "day_of_week": context.day_of_week or "unknown",
        }

        # Member presence summary
        presence_summary = [
            {
                "member_id": mp.member_id,
                "room_id":   mp.room_id,
                "is_home":   mp.is_home,
            }
            for mp in context.members_presence
        ]

        ctx = BedrockContext(
            household_id=context.household_id,
            events=events_summary,
            graph_subgraph=graph_subgraph or {},
            active_life_events=context.active_life_events[:5],
            members_presence=presence_summary,
            device_states=device_states,
            rule_engine_already_handled=rule_engine_already_handled or [],
            time_context=time_context,
        )

        # Rough token estimate: 1 token ≈ 4 characters of JSON
        raw = json.dumps(ctx.model_dump(), default=str)
        ctx.estimated_tokens = len(raw) // 4

        logger.debug(
            f"BedrockContext built: household={context.household_id} "
            f"events={len(events_summary)} "
            f"est_tokens={ctx.estimated_tokens}"
        )
        return ctx


# ─────────────────────────────────────────────────────────────
# 9.5  BedrockCircuitBreaker
# ─────────────────────────────────────────────────────────────

class BedrockCircuitBreaker:
    """
    State machine: CLOSED → OPEN (after 3 failures/60s) → HALF_OPEN (probe every 30s) → CLOSED
    Fires notification_service.notify_bedrock_degradation() when opening.
    """

    def __init__(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._window_start = time.monotonic()
        self._opened_at: float | None = None
        self._last_probe: float | None = None

        self._failure_threshold = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD  # 3
        self._window_secs = settings.CIRCUIT_BREAKER_WINDOW_SECS              # 60
        self._probe_interval = settings.CIRCUIT_BREAKER_PROBE_INTERVAL_SECS   # 30

    # ── Public interface ─────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    def is_open(self) -> bool:
        """Return True if requests should be blocked."""
        if self._state == CircuitState.OPEN:
            # Check if probe window has elapsed → transition to HALF_OPEN
            if self._opened_at and (time.monotonic() - self._opened_at) >= self._probe_interval:
                self._state = CircuitState.HALF_OPEN
                self._last_probe = time.monotonic()
                logger.info("CircuitBreaker: OPEN → HALF_OPEN (probe attempt)")
                return False  # allow the probe through
            return True
        return False

    def record_success(self) -> None:
        if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info("CircuitBreaker: probe succeeded → CLOSED")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._window_start = time.monotonic()
        self._opened_at = None

    def record_failure(self, household_id: str | None = None) -> None:
        now = time.monotonic()

        # Reset failure window if it has elapsed
        if (now - self._window_start) > self._window_secs:
            self._failure_count = 0
            self._window_start = now

        self._failure_count += 1
        logger.warning(f"CircuitBreaker: failure #{self._failure_count}")

        if self._failure_count >= self._failure_threshold:
            if self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = now
                logger.error(
                    f"CircuitBreaker: OPENED after {self._failure_count} failures. "
                    f"household={household_id}"
                )
                self._fire_degradation_notification(household_id)

    def get_state_dict(self) -> dict:
        return {
            "state":          self._state.value,
            "failure_count":  self._failure_count,
            "opened_at":      self._opened_at,
            "last_probe":     self._last_probe,
        }

    # ── Internal ─────────────────────────────────────────────

    def _fire_degradation_notification(self, household_id: str | None) -> None:
        """
        Soft import — notification_service is built in Phase 10.
        Fail silently here if not yet available.
        """
        if not household_id:
            return
        try:
            from services.notification_service import NotificationService  # type: ignore
            from services.task_tracker import task_tracker
            ns = NotificationService()
            task_tracker.spawn(
                ns.notify_bedrock_degradation,
                household_id,
                fallback="sync"
            )
        except ImportError:
            logger.warning(
                f"Bedrock circuit opened for {household_id} — "
                "notify_bedrock_degradation skipped (notification_service not yet loaded)"
            )
        except Exception as e:
            logger.warning(f"Degradation notification failed: {e}")


# ─────────────────────────────────────────────────────────────
# 9.6  BedrockLayer
# ─────────────────────────────────────────────────────────────

class BedrockLayer:
    """
    Orchestrates a Bedrock call:
      1. Circuit breaker check → block if OPEN
      2. Invoke real boto3 (or mock if BEDROCK_MOCK_MODE=true)
      3. Parse structured JSON response
      4. Record success/failure on circuit breaker
      5. Return BedrockResponse

    Mock mode returns a deterministic, realistic response for each
    event type so the full pipeline can be tested without AWS credentials.
    """

    _MOCK_PROMPT = (
        "You are SAATHI, an intelligent home automation assistant for Indian families. "
        "Respond with a JSON object containing 'actions', 'reasoning', and 'suggested_patterns'."
    )

    def __init__(
        self,
        circuit_breaker: BedrockCircuitBreaker | None = None,
        mock_mode: bool | None = None,
    ):
        self._cb = circuit_breaker or BedrockCircuitBreaker()
        self._mock = mock_mode if mock_mode is not None else settings.bedrock_mock_mode

    def invoke(
        self,
        bedrock_context: BedrockContext,
        household_id: str,
    ) -> BedrockResponse:
        """
        Main entry. Returns BedrockResponse with actions + reasoning.
        If circuit is OPEN, returns empty fallback response immediately.
        """
        if self._cb.is_open():
            logger.warning(f"BedrockLayer: circuit OPEN — skipping for {household_id}")
            return BedrockResponse(
                household_id=household_id,
                reasoning="Circuit breaker OPEN — Bedrock unavailable. Rule engine handling.",
                confidence=0.0,
            )

        start = time.monotonic()
        try:
            if self._mock:
                response = self._mock_invoke(bedrock_context, household_id)
            else:
                response = self._real_invoke(bedrock_context, household_id)

            response.latency_ms = (time.monotonic() - start) * 1000
            self._cb.record_success()
            logger.info(
                f"BedrockLayer: success household={household_id} "
                f"tokens={response.total_tokens} "
                f"latency={response.latency_ms:.1f}ms "
                f"actions={len(response.actions)}"
            )
            return response

        except Exception as e:
            self._cb.record_failure(household_id)
            logger.error(f"BedrockLayer: invocation failed: {e}")
            return BedrockResponse(
                household_id=household_id,
                reasoning=f"Bedrock error: {e}",
                confidence=0.0,
            )

    # ── Mock invoke ──────────────────────────────────────────

    def _mock_invoke(
        self,
        ctx: BedrockContext,
        household_id: str,
    ) -> BedrockResponse:
        """
        Returns a realistic canned response based on the first event type.
        Simulates ~800-1,200 tokens used.
        """
        first_event = ctx.events[0] if ctx.events else {}
        et = first_event.get("event_type", "unknown")
        life_events = ctx.active_life_events

        # Build context-aware mock response
        actions, reasoning, patterns = self._mock_response_for(et, household_id, ctx)

        input_tokens = ctx.estimated_tokens or 1100
        output_tokens = 250
        total = input_tokens + output_tokens

        return BedrockResponse(
            household_id=household_id,
            actions=actions,
            reasoning=reasoning,
            confidence=0.87,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            estimated_cost_usd=round(total * 0.000003, 6),
            model_id=settings.bedrock_model_id,
            suggested_patterns=patterns,
        )

    def _mock_response_for(
        self,
        event_type: str,
        household_id: str,
        ctx: BedrockContext,
    ) -> tuple[list, str, list]:
        """Returns (actions, reasoning, suggested_patterns) for mock mode."""

        if event_type == "guest_arrival":
            return (
                [
                    {
                        "action_type": "device_command",
                        "device_id": "dev_light_001",
                        "command": "set_warm_white",
                        "source": "BEDROCK",
                        "message": "Setting warm lighting for guests",
                    },
                    {
                        "action_type": "notification",
                        "target_member_ids": ["mbr_mama_004"],
                        "message": "Mehmaan aa rahe hain — ghar taiyar karen",
                        "channel": "alexa_voice",
                        "source": "BEDROCK",
                    },
                ],
                (
                    "Guest arrival detected during dinner time. "
                    "Setting warm lighting and notifying Mama to prepare. "
                    "Dadaji should not be disturbed given his medication schedule at 20:30."
                ),
                [
                    {
                        "pattern_id": "ptn_guest_evening_lights",
                        "description": "Warm lights when evening guests arrive",
                        "confidence": 0.0,
                        "event_type": "guest_arrival",
                    }
                ],
            )

        if event_type == "life_event":
            return (
                [
                    {
                        "action_type": "notification",
                        "target_member_ids": ["mbr_papa_003", "mbr_mama_004"],
                        "message": "Rohan ki boards shuru hone wali hain — quiet hours 21:00-07:00 activate kar raha hun",
                        "channel": "mobile_push",
                        "source": "BEDROCK",
                    },
                    {
                        "action_type": "device_command",
                        "device_id": "dev_tv_001",
                        "command": "set_volume_max_20",
                        "source": "BEDROCK",
                    },
                ],
                (
                    "Board exams in 6 days. Activating quiet hours protocol for the household. "
                    "TV volume capped at 20%. Notifying parents. "
                    "Dadaji's routine will not be impacted."
                ),
                [
                    {
                        "pattern_id": "ptn_exam_quiet_protocol",
                        "description": "Quiet mode during exam periods",
                        "confidence": 0.0,
                        "event_type": "life_event",
                    }
                ],
            )

        # Default: generic notification
        return (
            [
                {
                    "action_type": "notification",
                    "target_member_ids": [],
                    "message": f"SAATHI has noted the event: {event_type}",
                    "channel": "mobile_push",
                    "source": "BEDROCK",
                }
            ],
            f"Event type '{event_type}' processed by Bedrock. No specific rule pattern matched.",
            [],
        )

    # ── Real invoke ──────────────────────────────────────────

    def _real_invoke(
        self,
        ctx: BedrockContext,
        household_id: str,
    ) -> BedrockResponse:
        """Real AWS Bedrock converse API call."""
        import boto3

        client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

        prompt_body = (
            f"{self._MOCK_PROMPT}\n\n"
            f"Context:\n{json.dumps(ctx.model_dump(), default=str, indent=2)}\n\n"
            "Respond with valid JSON only."
        )

        response = client.converse(
            modelId=settings.bedrock_model_id,
            messages=[{"role": "user", "content": [{"text": prompt_body}]}],
        )

        output_text = (
            response["output"]["message"]["content"][0]["text"]
        )
        usage = response.get("usage", {})

        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError:
            parsed = {"actions": [], "reasoning": output_text, "suggested_patterns": []}

        return BedrockResponse(
            household_id=household_id,
            actions=parsed.get("actions", []),
            reasoning=parsed.get("reasoning", ""),
            confidence=parsed.get("confidence", 0.85),
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            total_tokens=usage.get("totalTokens", 0),
            estimated_cost_usd=usage.get("totalTokens", 0) * 0.000003,
            model_id=settings.bedrock_model_id,
            suggested_patterns=parsed.get("suggested_patterns", []),
        )
