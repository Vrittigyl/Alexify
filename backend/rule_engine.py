"""
rule_engine.py
Two-path rule engine: registry, evaluation, conflict resolution, and audit logging.

Components:
  RuleRegistry       — loads rules from DynamoDB, caches by (event_type, device_type)
  RuleEvaluationEngine — pure function: event + context + rule → EvaluationResult
  ConflictResolver   — priority: SAFETY > HEALTH > CUSTOM > PROMOTED > FLEET
  RuleEngine         — orchestrator: registry → evaluate → resolve → return Actions
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from config import settings
from db.dynamo_client import get_table
from schemas import Action, EvaluationResult, NormalizedEvent, Rule
from schemas.enums import ActionSource, ActionType, RuleType

logger = logging.getLogger(__name__)

# Priority map — lower int wins in a conflict
_PRIORITY = {
    RuleType.SAFETY:           1,
    RuleType.HEALTH:           2,
    RuleType.CUSTOM:           3,
    RuleType.PROMOTED_PATTERN: 4,
    RuleType.FLEET:            5,
}


# ─────────────────────────────────────────────────────────────
# 7.1  RuleRegistry
# ─────────────────────────────────────────────────────────────

class RuleRegistry:
    """
    In-memory cache of rules from DynamoDB HouseholdRules.
    Indexed by (event_type, device_type) for O(1) lookup.
    Refreshes every RULE_REGISTRY_REFRESH_SECS (default 5 min).
    """

    def __init__(self):
        self._table = get_table("household_rules")
        self._cache: dict[tuple, list[Rule]] = {}
        self._raw_rules: list[Rule] = []
        self._last_load: float = 0.0

    def _needs_refresh(self) -> bool:
        return (time.time() - self._last_load) > settings.RULE_REGISTRY_REFRESH_SECS

    def load(self, household_id: str) -> None:
        """
        Fetch all rules for this household (+ FLEET rules) from DynamoDB
        and build the in-memory (event_type, device_type) hashmap.
        """
        rules_raw = []
        for hh in [household_id, "FLEET"]:
            kwargs = {"KeyConditionExpression": Key("household_id").eq(hh)}
            while True:
                resp = self._table.query(**kwargs)
                for item in resp.get("Items", []):
                    item = _decimal_to_native(item)
                    try:
                        rules_raw.append(Rule(**item))
                    except Exception as e:
                        logger.warning(f"Skipping malformed rule {item.get('rule_id')}: {e}")
                last = resp.get("LastEvaluatedKey")
                if not last:
                    break
                kwargs["ExclusiveStartKey"] = last

        self._raw_rules = rules_raw
        self._cache = {}
        for rule in rules_raw:
            trigger = rule.trigger
            key = (
                trigger.event_type.value if trigger.event_type else None,
                trigger.device_type.value if trigger.device_type else None,
            )
            self._cache.setdefault(key, []).append(rule)

        self._last_load = time.time()
        logger.info(f"RuleRegistry loaded: {len(rules_raw)} rules for household={household_id}")

    def get_candidates(
        self,
        household_id: str,
        event: NormalizedEvent,
        force_reload: bool = False,
    ) -> list[Rule]:
        """Return rules that could match this event. Refreshes cache if stale."""
        if force_reload or self._needs_refresh():
            self.load(household_id)

        event_type_val = event.event_type.value if event.event_type else None
        device_type_val = event.device_type.value if event.device_type else None

        candidates = []
        # Exact match (event_type, device_type)
        candidates.extend(self._cache.get((event_type_val, device_type_val), []))
        # Event-type-only rules (no device constraint)
        candidates.extend(self._cache.get((event_type_val, None), []))
        # Device-type-only rules (no event constraint)
        candidates.extend(self._cache.get((None, device_type_val), []))
        # Universal rules (neither constrained)
        candidates.extend(self._cache.get((None, None), []))

        # Deduplicate by rule_id
        seen = set()
        unique = []
        for r in candidates:
            if r.rule_id not in seen:
                seen.add(r.rule_id)
                unique.append(r)
        return unique

    def all_rules(self) -> list[Rule]:
        return list(self._raw_rules)


# ─────────────────────────────────────────────────────────────
# 7.2  RuleEvaluationEngine
# ─────────────────────────────────────────────────────────────

class RuleEvaluationEngine:
    """
    Pure evaluation function: no DynamoDB calls, no side effects.
    evaluate(event, context, rule) → EvaluationResult
    """

    def __init__(self):
        # Instance-level cache — NOT class-level. Class variables are shared
        # across all instances in the same process, which causes the second
        # RuleEngine.run() call to see the key from the first and suppress.
        self._idempotency_cache: dict[str, float] = {}

    def evaluate(
        self,
        event: NormalizedEvent,
        context: dict[str, Any],
        rule: Rule,
    ) -> EvaluationResult:
        """
        Evaluate a single rule against an event + household context.
        Returns EvaluationResult with match=True and actions if the rule fires.
        """
        # Step 1: Trigger match
        if not self._trigger_matches(event, rule):
            return EvaluationResult(match=False)

        # Step 2: Condition loop
        for condition in rule.conditions:
            passed, should_escalate = self._evaluate_condition(condition, event, context)
            if not passed:
                if should_escalate:
                    return EvaluationResult(
                        match=False,
                        escalate_to_bedrock=True,
                        reason=f"Condition failed with on_fail=escalate_to_bedrock: field={condition.field}",
                    )
                return EvaluationResult(match=False, reason=f"Condition failed: {condition.field}")

        # Step 3: Idempotency window check
        if rule.idempotency_window_secs:
            idem_key = self._idempotency_key(event.household_id, rule.rule_id)
            if self._is_idempotent(idem_key, rule.idempotency_window_secs):
                return EvaluationResult(
                    match=False,
                    reason=f"Idempotency window active for rule {rule.rule_id}",
                )
            self._mark_idempotent(idem_key)

        # Step 4: Build action from rule
        return EvaluationResult(
            match=True,
            actions=[rule.action],
            source=ActionSource.RULE_ENGINE,
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            explanation=f"Rule '{rule.name or rule.rule_id}' matched",
        )

    def _trigger_matches(self, event: NormalizedEvent, rule: Rule) -> bool:
        """Check if the event matches the rule's trigger definition."""
        trigger = rule.trigger

        # Event type check
        if trigger.event_type and event.event_type != trigger.event_type:
            return False

        # Device type check
        if trigger.device_type and event.device_type != trigger.device_type:
            return False

        # Field/op/value check
        if trigger.field and trigger.op and trigger.value is not None:
            field_val = event.payload.get(trigger.field)
            if field_val is None:
                return False
            if not self._compare(field_val, trigger.op, trigger.value):
                return False

        return True

    def _evaluate_condition(
        self,
        condition: Any,
        event: NormalizedEvent,
        context: dict[str, Any],
    ) -> tuple[bool, bool]:
        """
        Returns (passed: bool, should_escalate: bool).
        Looks up condition.field in event.payload or context.
        """
        on_fail = getattr(condition, "on_fail", None) or ""
        field = condition.field
        op = condition.op
        value = condition.value

        # Resolve field value — try payload first, then context
        if field.startswith("context."):
            ctx_key = field[len("context."):]
            field_val = context.get(ctx_key)
        else:
            field_val = event.payload.get(field)

        if field_val is None:
            # Missing field — skip if on_fail == "skip", else fail
            if on_fail == "skip":
                return True, False
            return False, on_fail == "escalate_to_bedrock"

        try:
            passed = self._compare(field_val, op, value)
        except Exception:
            return False, False

        if not passed:
            return False, on_fail == "escalate_to_bedrock"

        return True, False

    @staticmethod
    def _compare(field_val: Any, op: str, value: Any) -> bool:
        try:
            if op == "eq":
                return field_val == value
            if op == "neq":
                return field_val != value
            if op == "gte":
                return float(field_val) >= float(value)
            if op == "lte":
                return float(field_val) <= float(value)
            if op == "gt":
                return float(field_val) > float(value)
            if op == "lt":
                return float(field_val) < float(value)
            if op == "in":
                return field_val in value
            if op == "not_in":
                return field_val not in value
            if op == "contains_member_home":
                # context.members_presence: [{member_id, is_home}]
                if isinstance(field_val, list):
                    return any(
                        m.get("member_id") == value and m.get("is_home", True)
                        for m in field_val
                    )
            if op == "contains_event":
                if isinstance(field_val, list):
                    return any(e.get("event") == value for e in field_val)
                return False
            if op == "not_contains":
                if isinstance(field_val, list):
                    return not any(e.get("event") == value or e == value for e in field_val)
                return True
        except (TypeError, ValueError):
            return False
        return False

    def _idempotency_key(self, household_id: str, rule_id: str) -> str:
        return f"{household_id}:{rule_id}"

    def _is_idempotent(self, key: str, window_secs: int) -> bool:
        expiry = self._idempotency_cache.get(key)
        return expiry is not None and expiry > time.time()

    def _mark_idempotent(self, key: str) -> None:
        self._idempotency_cache[key] = time.time() + settings.IDEMPOTENCY_WINDOW_SECS


# ─────────────────────────────────────────────────────────────
# 7.3  ConflictResolver
# ─────────────────────────────────────────────────────────────

class ConflictResolver:
    """
    Resolves conflicts between multiple matched rules.
    Priority order: SAFETY > HEALTH > CUSTOM > PROMOTED_PATTERN > FLEET
    Same type: higher rule_version wins.
    """

    def resolve(self, matched_rules: list[tuple[Rule, EvaluationResult]]) -> list[tuple[Rule, EvaluationResult]]:
        """
        Returns the winning set of rules. Safety rules are never suppressed —
        they're always included. Other types are resolved by priority.
        """
        if not matched_rules:
            return []

        # Separate safety rules (always execute)
        safety = [(r, er) for r, er in matched_rules if r.rule_type == RuleType.SAFETY]
        non_safety = [(r, er) for r, er in matched_rules if r.rule_type != RuleType.SAFETY]

        if not non_safety:
            return safety

        # Find the highest priority among non-safety rules
        best_priority = min(_PRIORITY.get(r.rule_type, 99) for r, _ in non_safety)
        top_tier = [(r, er) for r, er in non_safety if _PRIORITY.get(r.rule_type, 99) == best_priority]

        # If multiple rules at same priority, highest rule_version wins
        winner = max(top_tier, key=lambda x: x[0].rule_version)

        conflicts = [r for r, _ in top_tier if r.rule_id != winner[0].rule_id]
        if conflicts:
            logger.info(
                f"Conflict resolved: winner={winner[0].rule_id} "
                f"over {[r.rule_id for r in conflicts]}"
            )

        return safety + [winner]


# ─────────────────────────────────────────────────────────────
# 7.4  ConflictAuditLog writer
# ─────────────────────────────────────────────────────────────

async def _log_conflict(conflict: dict[str, Any]) -> None:
    """Non-blocking write to ConflictAuditLog."""
    try:
        table = get_table("conflict_audit_log")
        table.put_item(Item={
            "conflict_id": f"cfl_{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **conflict,
        })
    except Exception as e:
        logger.warning(f"ConflictAuditLog write failed (non-critical): {e}")


# ─────────────────────────────────────────────────────────────
# 7.5  RuleEngine — orchestrator
# ─────────────────────────────────────────────────────────────

class RuleEngine:
    """
    Orchestrates the full rule evaluation pipeline:
    registry lookup → evaluate each rule → conflict resolution → return Actions
    All returned actions are tagged source=RULE_ENGINE.
    """

    def __init__(self):
        self._registry = RuleRegistry()
        self._evaluator = RuleEvaluationEngine()
        self._resolver = ConflictResolver()

    def run(
        self,
        event: NormalizedEvent,
        context: dict[str, Any] | None = None,
    ) -> list[Action]:
        """
        Run the rule engine against an event.
        Returns a list of Actions (may be empty).
        Also sets escalate_to_bedrock=True on the event if a condition demands it.
        """
        context = context or {}
        candidates = self._registry.get_candidates(event.household_id, event)

        if not candidates:
            logger.debug(f"No rule candidates for event {event.event_id}")
            return []

        # Evaluate all candidates
        matched: list[tuple[Rule, EvaluationResult]] = []
        escalate = False

        for rule in candidates:
            result = self._evaluator.evaluate(event, context, rule)
            if result.escalate_to_bedrock:
                escalate = True
            if result.match:
                matched.append((rule, result))

        if escalate:
            # Signal to caller that Bedrock should also be involved
            event.requires_ai = True

        if not matched:
            return []

        # Resolve conflicts
        winners = self._resolver.resolve(matched)

        # Log conflicts if any were suppressed
        if len(matched) > len(winners):
            suppressed = [r.rule_id for r, _ in matched if (r, _) not in winners]
            asyncio.create_task(
                _log_conflict({
                    "event_id": event.event_id,
                    "household_id": event.household_id,
                    "winning_rules": [r.rule_id for r, _ in winners],
                    "suppressed_rules": suppressed,
                })
            ) if asyncio.get_event_loop().is_running() else None

        # Build Action objects
        actions: list[Action] = []
        for rule, result in winners:
            for rule_action in result.actions:
                actions.append(Action(
                    household_id=event.household_id,
                    action_type=rule_action.type,
                    source=ActionSource.RULE_ENGINE,
                    device_id=rule_action.target_device_id,
                    command=rule_action.command,
                    target_member_ids=rule_action.target_member_ids or [],
                    message=rule_action.message_template,
                    channel=rule_action.channel,
                    rule_id=result.rule_id,
                    event_id=event.event_id,
                ))

        logger.info(
            f"RuleEngine: event={event.event_id}, "
            f"candidates={len(candidates)}, "
            f"matched={len(matched)}, "
            f"actions={len(actions)}"
        )
        return actions


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _decimal_to_native(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_native(i) for i in obj]
    return obj
