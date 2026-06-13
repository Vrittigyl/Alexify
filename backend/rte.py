"""
rte.py
Reasoning Trigger Evaluator — 4-stage pipeline that decides how to route
each NormalizedEvent: RULE_ENGINE, BEDROCK, or SUPPRESS.

Stages:
  Stage 1: Does any rule in the registry match? → RULE_ENGINE
  Stage 2: Does a PROMOTED pattern match?       → RULE_ENGINE
  Stage 3: Is complexity score >= threshold?     → BEDROCK, else SUPPRESS
  Stage 4: Default fallback                      → SUPPRESS

First stage to give a definitive answer wins. Each stage is a pure function.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings
from db.dynamo_client import get_table
from rule_engine import RuleRegistry
from schemas import NormalizedEvent, RTEDecision
from schemas.enums import ConfidenceBand, EventType, RouteDecision

logger = logging.getLogger(__name__)

# Events that always route to Bedrock regardless of score
_AI_REQUIRED_EVENT_TYPES = set(settings.AI_REQUIRED_EVENT_TYPES)


def _compare_trigger(field_val, op: str, value) -> bool:
    """Minimal trigger comparison — mirrors RuleEvaluationEngine._compare()."""
    try:
        if op == "eq":    return field_val == value
        if op == "neq":   return field_val != value
        if op == "gte":   return float(field_val) >= float(value)
        if op == "lte":   return float(field_val) <= float(value)
        if op == "gt":    return float(field_val) > float(value)
        if op == "lt":    return float(field_val) < float(value)
        if op == "in":    return field_val in value
        if op == "not_in": return field_val not in value
    except (TypeError, ValueError):
        return False
    return False



# ─────────────────────────────────────────────────────────────
# 8.1  Stage 1 — Rule Registry Check
# ─────────────────────────────────────────────────────────────

class Stage1_RuleRegistryCheck:
    """
    Check if any active rule in the registry matches this event.
    If yes: route to RULE_ENGINE immediately — no scoring needed.
    """

    def __init__(self, rule_registry: RuleRegistry):
        self._registry = rule_registry

    def check(
        self,
        event: NormalizedEvent,
    ) -> tuple[RouteDecision | None, str | None]:
        """
        Returns (RouteDecision, matched_rule_id) or (None, None) to continue.
        Evaluates the trigger field/op/value against the event payload so that
        a rule candidate that doesn't field-match doesn't inflate RULE_ENGINE routing.
        """
        candidates = self._registry.get_candidates(event.household_id, event)
        if not candidates:
            return None, None

        for rule in candidates:
            trigger = rule.trigger
            # If the rule has a field/op/value check, evaluate it now
            if trigger.field and trigger.op and trigger.value is not None:
                field_val = event.payload.get(trigger.field)
                if field_val is None:
                    continue
                try:
                    if not _compare_trigger(field_val, trigger.op, trigger.value):
                        continue
                except Exception:
                    continue

            # Trigger passes (or has no field constraint) — this rule will fire
            logger.debug(f"Stage1: matched rule {rule.rule_id} for event {event.event_id}")
            return RouteDecision.RULE_ENGINE, rule.rule_id

        # Candidates exist but none pass the trigger field check
        return None, None



# ─────────────────────────────────────────────────────────────
# 8.2  Stage 2 — Promoted Pattern Check
# ─────────────────────────────────────────────────────────────

class Stage2_PatternPromotionCheck:
    """
    Check if a PROMOTED pattern in the household matches this event's
    device_type + event_type combination.
    PROMOTED patterns are lightweight enough to route via the rule engine.
    """

    def __init__(self, promoted_cache: list[dict] | None = None):
        # Cache is injected (populated from DynamoDB by the caller)
        self._promoted: list[dict] = promoted_cache or []

    def update_cache(self, patterns: list[dict]) -> None:
        self._promoted = [
            p for p in patterns
            if p.get("confidence_band") == ConfidenceBand.PROMOTED.value
        ]

    def check(
        self,
        event: NormalizedEvent,
    ) -> tuple[RouteDecision | None, str | None]:
        """
        Returns (RULE_ENGINE, pattern_id) if a promoted pattern matches,
        otherwise (None, None).
        """
        et = event.event_type.value if event.event_type else None
        dt = event.device_type.value if event.device_type else None

        for pattern in self._promoted:
            p_et = pattern.get("event_type")
            p_dt = pattern.get("device_type")

            # Match if event_type and device_type both match (or pattern has None = wildcard)
            et_match = (p_et is None) or (p_et == et)
            dt_match = (p_dt is None) or (p_dt == dt)

            if et_match and dt_match:
                logger.debug(
                    f"Stage2: promoted pattern {pattern['pattern_id']} matched event {event.event_id}"
                )
                return RouteDecision.RULE_ENGINE, pattern["pattern_id"]

        return None, None


# ─────────────────────────────────────────────────────────────
# 8.3  Stage 3 — Complexity Scorer
# ─────────────────────────────────────────────────────────────

class Stage3_ComplexityScorer:
    """
    Computes a complexity score from the event and household context.
    Score >= threshold → BEDROCK
    Score < threshold  → SUPPRESS (not complex enough to bother Bedrock)

    Score weights (from config):
      +100  event requires AI (life_event, guest_arrival, etc.)
      +25   per active life event in context
      +30   per health constraint on affected members
      +20   per device conflict in context
      +15   per affected member
      +15   multi-device event (affects > 1 device)
    """

    def check(
        self,
        event: NormalizedEvent,
        context: dict[str, Any],
    ) -> tuple[RouteDecision, int, dict[str, int]]:
        """
        Returns (RouteDecision, total_score, score_breakdown).
        Always returns a definitive decision (BEDROCK or SUPPRESS).
        """
        breakdown: dict[str, int] = {}
        score = 0

        # AI-required event type (always Bedrock regardless of other scores)
        if event.event_type.value in _AI_REQUIRED_EVENT_TYPES or event.requires_ai:
            score += settings.RTE_SCORE_AI_REQUIRED
            breakdown["ai_required"] = settings.RTE_SCORE_AI_REQUIRED

        # Active life events in context
        life_events = context.get("active_life_events", [])
        if life_events:
            le_score = len(life_events) * settings.RTE_SCORE_PER_LIFE_EVENT
            score += le_score
            breakdown["life_events"] = le_score

        # Health constraints on affected members
        health_constraints = context.get("health_constraints", [])
        if health_constraints:
            hc_score = len(health_constraints) * settings.RTE_SCORE_HEALTH_CONSTRAINT
            score += hc_score
            breakdown["health_constraints"] = hc_score

        # Device conflicts
        conflicts = context.get("device_conflicts", [])
        if conflicts:
            cf_score = len(conflicts) * settings.RTE_SCORE_PER_CONFLICT
            score += cf_score
            breakdown["conflicts"] = cf_score

        # Affected members
        members = event.affected_member_ids or context.get("affected_member_ids", [])
        if members:
            mb_score = len(members) * settings.RTE_SCORE_PER_MEMBER
            score += mb_score
            breakdown["members"] = mb_score

        # Multi-device
        device_ids = context.get("affected_device_ids", [])
        if len(device_ids) > 1:
            score += settings.RTE_SCORE_MULTI_DEVICE
            breakdown["multi_device"] = settings.RTE_SCORE_MULTI_DEVICE

        threshold = settings.bedrock_complexity_threshold
        breakdown["total"] = score
        breakdown["threshold"] = threshold

        if score >= threshold:
            logger.debug(f"Stage3: score={score} >= threshold={threshold} → BEDROCK")
            return RouteDecision.BEDROCK, score, breakdown

        logger.debug(f"Stage3: score={score} < threshold={threshold} → SUPPRESS")
        return RouteDecision.SUPPRESS, score, breakdown


# ─────────────────────────────────────────────────────────────
# 8.4  Stage 4 — Default
# ─────────────────────────────────────────────────────────────

class Stage4_Default:
    """Safety net — if all prior stages pass through, suppress."""

    def check(self) -> RouteDecision:
        return RouteDecision.SUPPRESS


# ─────────────────────────────────────────────────────────────
# 8.6  Audit log writer
# ─────────────────────────────────────────────────────────────

async def _audit_log(decision: RTEDecision) -> None:
    """Non-blocking write to RTEAuditLog with 90-day TTL."""
    try:
        from decimal import Decimal
        table = get_table("rte_audit_log")
        ttl_epoch = int(time.time()) + (settings.RTE_AUDIT_TTL_DAYS * 86400)

        item = {
            "event_id": decision.event_id,
            "timestamp": decision.timestamp.isoformat(),
            "household_id": decision.household_id,
            "event_type": decision.event_type.value,
            "route": decision.route.value,
            "stage_decided": decision.stage_decided,
            "complexity_score": decision.complexity_score,
            "audit_expiry": ttl_epoch,
        }
        if decision.device_type:
            item["device_type"] = decision.device_type.value
        if decision.rule_matched:
            item["rule_matched"] = decision.rule_matched
        if decision.pattern_matched:
            item["pattern_matched"] = decision.pattern_matched
        if decision.score_breakdown:
            item["score_breakdown"] = {
                k: Decimal(str(v)) for k, v in decision.score_breakdown.items()
            }
        if decision.latency_ms:
            item["latency_ms"] = Decimal(str(decision.latency_ms))

        table.put_item(Item=item)
        logger.debug(f"RTEAuditLog written: event={decision.event_id}, route={decision.route.value}")
    except Exception as e:
        logger.warning(f"RTEAuditLog write failed (non-critical): {e}")


# ─────────────────────────────────────────────────────────────
# 8.5  RTE — orchestrator
# ─────────────────────────────────────────────────────────────

class RTE:
    """
    Reasoning Trigger Evaluator.
    Runs all 4 stages in order, stops at the first definitive answer.
    Logs every decision to RTEAuditLog asynchronously.
    """

    def __init__(
        self,
        rule_registry: RuleRegistry | None = None,
        promoted_patterns: list[dict] | None = None,
    ):
        _registry = rule_registry or RuleRegistry()
        self._stage1 = Stage1_RuleRegistryCheck(_registry)
        self._stage2 = Stage2_PatternPromotionCheck(promoted_patterns)
        self._stage3 = Stage3_ComplexityScorer()
        self._stage4 = Stage4_Default()

    def update_promoted_cache(self, patterns: list[dict]) -> None:
        self._stage2.update_cache(patterns)

    def classify(
        self,
        event: NormalizedEvent,
        context: dict[str, Any] | None = None,
    ) -> RTEDecision:
        """
        Route a NormalizedEvent through all 4 stages.
        Returns an RTEDecision with route, stage, score, and traceability.
        Also fires an async audit log write (non-blocking).
        """
        context = context or {}
        start = time.monotonic()

        score = 0
        breakdown: dict[str, int] = {}
        rule_matched = None
        pattern_matched = None

        # Stage 1
        route, rule_matched = self._stage1.check(event)
        if route is not None:
            stage = 1
        else:
            # Stage 2
            route, pattern_matched = self._stage2.check(event)
            if route is not None:
                stage = 2
            else:
                # Stage 3
                route, score, breakdown = self._stage3.check(event, context)
                stage = 3
                if route is None:
                    # Stage 4 (shouldn't reach here — Stage3 always returns)
                    route = self._stage4.check()
                    stage = 4

        latency_ms = (time.monotonic() - start) * 1000

        decision = RTEDecision(
            event_id=event.event_id,
            household_id=event.household_id,
            event_type=event.event_type,
            device_type=event.device_type,
            route=route,
            stage_decided=stage,
            complexity_score=score,
            rule_matched=rule_matched,
            pattern_matched=pattern_matched,
            score_breakdown=breakdown if breakdown else None,
            latency_ms=latency_ms,
        )

        logger.info(
            f"RTE: event={event.event_id} "
            f"route={route.value} stage={stage} "
            f"score={score} latency={latency_ms:.1f}ms"
        )

        # Fire-and-forget audit log
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            loop.create_task(_audit_log(decision))
        else:
            # Sync fallback for non-async contexts (scripts, tests)
            asyncio.run(_audit_log(decision))

        return decision
