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


def _find_device_id(
    household_id: str,
    device_type: str,
    room: str | None = None,
    fallback: str = "",
) -> str:
    """Resolve a device node_id from the household graph by type and optional room."""
    try:
        from graph_repository import GraphRepository
        g = GraphRepository().load_graph(household_id)
        matches: list[str] = []
        for node_id, attrs in g.nodes(data=True):
            if attrs.get("node_type") != "device":
                continue
            if attrs.get("device_type") != device_type:
                continue
            if room and attrs.get("room") != room:
                continue
            matches.append(node_id)
        if matches:
            return matches[0]
    except Exception as exc:
        logger.debug(f"BedrockLayer: device lookup failed ({device_type}, {room}): {exc}")
    return fallback


# ─────────────────────────────────────────────────────────────
# 9.4  ContextBuilder
# ─────────────────────────────────────────────────────────────

class ContextBuilder:
    """
    Converts a batch of NormalizedEvents + HouseholdContext into a
    token-efficient BedrockContext.

    Token budget target: <400 tokens.
    Strategy:
      - Events: only event_type + device_type + the 3 most relevant payload keys
      - Device states: capped at 3 entries, only (state, device_type) fields
      - Members presence: only member_id + is_home (drop room_id, detected_at)
      - Life events: capped at 3, only (event_id, event_type, remaining_days)
      - Graph subgraph: always excluded (too expensive, not used by prompt)
      - No None values, no empty collections
      - Serialised with no indentation
    """

    # Payload keys that are actually useful for reasoning — everything else is dropped
    _PAYLOAD_KEEP = {"tank_level_percent", "whistle_count", "running_minutes",
                     "door_open_seconds", "temperature_c", "volume_percent",
                     "state", "event", "member_id", "remaining_days",
                     "guest_count", "relation", "festival"}

    def build_bedrock_context(
        self,
        batch: list[NormalizedEvent],
        context: HouseholdContext,
        graph_subgraph: dict[str, Any] | None = None,
        rule_engine_already_handled: list[str] | None = None,
    ) -> BedrockContext:

        # ── Events: drop event_id, clip payload to relevant keys ─────
        events_summary = []
        for ev in batch:
            entry: dict[str, Any] = {
                "event_type": ev.event_type.value,
            }
            if ev.device_type:
                entry["device_type"] = ev.device_type.value
            if ev.impact_level:
                entry["impact"] = ev.impact_level.value
            trimmed_payload = {
                k: v for k, v in ev.payload.items()
                if k in self._PAYLOAD_KEEP and v is not None
            }
            if trimmed_payload:
                entry["payload"] = trimmed_payload
            events_summary.append(entry)

        # ── Device states: cap 3, only state + device_type ───────────
        device_states: dict[str, Any] = {}
        for dev_id, state_dict in list(context.device_states.items())[:3]:
            slim = {k: v for k, v in state_dict.items()
                    if k in ("state", "device_type") and v is not None}
            if slim:
                device_states[dev_id] = slim

        # ── Time context ─────────────────────────────────────────────
        time_context: dict[str, str] = {}
        if context.ist_time:
            time_context["time"] = context.ist_time
        if context.time_of_day:
            time_context["period"] = context.time_of_day
        if context.day_of_week:
            time_context["day"] = context.day_of_week

        # ── Presence: only member_id + is_home ───────────────────────
        presence_summary = [
            {"member_id": mp.member_id, "home": mp.is_home}
            for mp in context.members_presence
        ]

        # ── Life events: cap 3, only actionable fields ───────────────
        life_events_slim = [
            {k: v for k, v in le.items()
             if k in ("event_id", "event_type", "remaining_days", "constraints") and v is not None}
            for le in context.active_life_events[:3]
        ]

        ctx = BedrockContext(
            household_id=context.household_id,
            events=events_summary,
            graph_subgraph={},                              # always excluded
            active_life_events=life_events_slim,
            members_presence=presence_summary,
            device_states=device_states,
            rule_engine_already_handled=rule_engine_already_handled or [],
            time_context=time_context,
        )

        # Token estimate: 1 token ≈ 4 chars, no indent serialisation
        raw = json.dumps(ctx.model_dump(), default=str, separators=(",", ":"))
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
# Module-level helpers
# ─────────────────────────────────────────────────────────────

def _normalise_suggested_patterns(raw: Any) -> list[dict]:
    """
    C. Normalise whatever the model returns for suggested_patterns into
    list[dict[str, Any]] so BedrockResponse never sees invalid types.

    Handles:
      - list[dict]  → returned as-is (already correct)
      - list[str]   → each string becomes {"pattern_id": s, "description": s,
                                            "confidence": 0.0, "event_type": None}
      - None / non-list → empty list
      - mixed list  → each element normalised individually
    """
    if not isinstance(raw, list):
        return []

    result: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            # Model returned a bare string like "evening_reception" — promote it
            logger.warning(
                f"BedrockLayer: suggested_patterns contained a string {item!r}; "
                "promoting to minimal dict. Consider improving the prompt."
            )
            result.append({
                "pattern_id":  item,
                "description": item,
                "confidence":  0.0,
                "event_type":  None,
            })
        else:
            logger.warning(
                f"BedrockLayer: skipping unexpected suggested_pattern type "
                f"{type(item).__name__}: {item!r}"
            )
    return result


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

    # ── System prompt sent to Bedrock ──────────────────────────────────────────
    # Kept deliberately minimal to save output tokens.
    # The JSON schema in the prompt tells the model exactly what to return so it
    # doesn't waste tokens on prose, markdown fences, or explanations.
    _SYSTEM_PROMPT = (
        "You are SAATHI, a smart home assistant for Indian families. "
        "Return ONLY valid JSON. No markdown, no code fences, no explanations.\n"
        "Schema:\n"
        '{"actions":[{"action_type":"device_command|notification","device_id":"...","command":"...","target_member_ids":[],"message":"...","channel":"alexa_voice|mobile_push|whatsapp"}],'
        '"reasoning":"one sentence","confidence":0.0,'
        '"suggested_patterns":[{"pattern_id":"...","description":"...","confidence":0.0,"event_type":"..."}]}'
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
            light_id = _find_device_id(household_id, "light", "Living Room", "dev_light_001")
            ac_id = _find_device_id(
                household_id, "ac", "Living Room",
                _find_device_id(household_id, "ac", None, "dev_ac_001"),
            )
            return (
                [
                    {
                        "action_type": "device_command",
                        "device_id": light_id,
                        "command": "set_warm_white",
                        "source": "BEDROCK",
                        "message": "Setting warm lighting for guests",
                    },
                    {
                        "action_type": "device_command",
                        "device_id": ac_id,
                        "command": "set_temp_22",
                        "source": "BEDROCK",
                        "message": "Pre-cooling living room to 22C",
                    },
                    {
                        "action_type": "notification",
                        "target_member_ids": ["mbr_papa_003"],
                        "message": "Mehmaan aa rahe hain - living room AC 22C par set kar diya hai. Fridge me cold drinks check kar lijiye.",
                        "channel": "whatsapp",
                        "source": "BEDROCK",
                    },
                ],
                (
                    "Guest arrival detected during dinner time. "
                    "Pre-cooling the living room, setting warm lighting, and notifying Mama to prepare cold drinks. "
                    "Dadaji should not be disturbed given his medication schedule at 20:30."
                ),
                [
                    {
                        "pattern_id": "ptn_guest_evening_lights",
                        "description": "Warm lights and AC when evening guests arrive",
                        "confidence": 0.0,
                        "event_type": "guest_arrival",
                    }
                ],
            )

        if event_type == "life_event":
            tv_id = _find_device_id(household_id, "television", "Living Room", "dev_tv_001")
            ac_id = _find_device_id(
                household_id, "ac", "Study",
                _find_device_id(household_id, "ac", "Bedroom 1", "dev_ac_002"),
            )
            return (
                [
                    {
                        "action_type": "notification",
                        "target_member_ids": ["mbr_papa_003", "mbr_mama_004"],
                        "message": "Rohan ki boards 6 din mein shuru hone wali hain. AC ko 24C par set kar diya hai aur TV volume limit kar diya hai.",
                        "channel": "whatsapp",
                        "source": "BEDROCK",
                    },
                    {
                        "action_type": "device_command",
                        "device_id": tv_id,
                        "command": "set_volume_max_20",
                        "source": "BEDROCK",
                    },
                    {
                        "action_type": "device_command",
                        "device_id": ac_id,
                        "command": "set_temp_24",
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
        """
        Real AWS Bedrock converse API call.

        Hardening applied here (not in the schema) so BedrockResponse always
        receives clean data and never raises a Pydantic validation error:

          A. Log the raw model output before any parsing.
          B. Strip markdown code fences the model sometimes emits.
          C. Normalise suggested_patterns: accept list[str] or list[dict];
             strings are promoted to minimal dicts so Pydantic is happy.
          D. Defensive fallback: if JSON parsing fails entirely, return
             actions=[], patterns=[], and keep the raw text as reasoning.
        """
        import boto3

        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

        # ── Build the prompt ─────────────────────────────────────────
        # Serialise context without indentation and without None/empty
        # fields to keep the input token count as low as possible.
        ctx_dict = {
            k: v for k, v in ctx.model_dump().items()
            if v not in (None, [], {}, "")
        }
        context_json = json.dumps(ctx_dict, default=str, separators=(",", ":"))

        prompt_body = (
            f"{self._SYSTEM_PROMPT}\n\n"
            f"Context: {context_json}"
        )

        # ── Invoke ───────────────────────────────────────────────────
        response = client.converse(
            modelId=settings.bedrock_model_id,
            messages=[{"role": "user", "content": [{"text": prompt_body}]}],
        )

        output_text: str = response["output"]["message"]["content"][0]["text"]
        usage = response.get("usage", {})

        # A. Log raw output for debugging — always, before any processing
        logger.info(f"RAW BEDROCK OUTPUT: {output_text}")

        # ── Parse ────────────────────────────────────────────────────
        parsed = self._parse_model_output(output_text)

        # C. Normalise suggested_patterns
        raw_patterns = parsed.get("suggested_patterns", [])
        safe_patterns = _normalise_suggested_patterns(raw_patterns)

        return BedrockResponse(
            household_id=household_id,
            actions=parsed.get("actions", []),
            reasoning=parsed.get("reasoning", ""),
            confidence=float(parsed.get("confidence", 0.85)),
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            total_tokens=usage.get("totalTokens", 0),
            estimated_cost_usd=usage.get("totalTokens", 0) * 0.000003,
            model_id=settings.bedrock_model_id,
            suggested_patterns=safe_patterns,
        )

    # ── Shared parsing helpers ────────────────────────────────

    @staticmethod
    def _parse_model_output(output_text: str) -> dict:
        """
        B + D: Strip markdown fences, attempt JSON parse.
        On any failure keep the text as reasoning and return safe defaults.
        """
        # Strip markdown code fences: ```json ... ``` or ``` ... ```
        text = output_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]          # drop opening fence line
            text = text.rsplit("```", 1)[0].strip()  # drop closing fence

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected dict, got {type(parsed).__name__}")
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                f"BedrockLayer: JSON parse failed ({exc}). "
                f"Raw output length={len(output_text)}. Using safe defaults."
            )
            # D. Defensive fallback — never propagate a parse error upward
            return {
                "actions": [],
                "reasoning": output_text[:500],   # cap to avoid huge strings
                "confidence": 0.0,
                "suggested_patterns": [],
            }
