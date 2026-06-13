"""
tests/test_rule_engine.py
10 scenario tests for the Rule Engine.
Run: pytest tests/test_rule_engine.py -v
All tests use in-memory rule/event construction — no DynamoDB reads needed.
"""

import time
import pytest

from schemas import NormalizedEvent, Rule, EvaluationResult
from schemas.enums import (
    ActionSource, ActionType, DeviceType, EventType,
    ImpactLevel, NotificationChannel, RuleType,
)
from schemas.rules import RuleAction, RuleCondition, RuleTrigger
from engines.rule_engine import RuleEvaluationEngine, ConflictResolver, RuleEngine, RuleRegistry

HH_ID = "hh_xk92p_sharma"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def make_event(
    event_type=EventType.DEVICE_STATE,
    device_type=DeviceType.WATER_MOTOR,
    device_id="dev_water_motor_001",
    payload=None,
    requires_ai=False,
) -> NormalizedEvent:
    return NormalizedEvent(
        household_id=HH_ID,
        event_type=event_type,
        device_type=device_type,
        device_id=device_id,
        payload=payload or {},
        requires_ai=requires_ai,
    )


def make_rule(
    rule_id="rl_test",
    rule_type=RuleType.SAFETY,
    trigger_field=None,
    trigger_op=None,
    trigger_value=None,
    event_type=EventType.DEVICE_STATE,
    device_type=DeviceType.WATER_MOTOR,
    conditions=None,
    action_type=ActionType.DEVICE_COMMAND,
    command="turn_off",
    idempotency_window_secs=None,
    rule_version=1,
) -> Rule:
    return Rule(
        household_id="FLEET",
        rule_id=rule_id,
        rule_type=rule_type,
        rule_version=rule_version,
        trigger=RuleTrigger(
            event_type=event_type,
            device_type=device_type,
            field=trigger_field,
            op=trigger_op,
            value=trigger_value,
        ),
        conditions=conditions or [],
        action=RuleAction(
            type=action_type,
            command=command,
            target_device_id="dev_water_motor_001",
            message_template="Test action fired",
            channel=NotificationChannel.MOBILE_PUSH,
        ),
        idempotency_window_secs=idempotency_window_secs,
    )


# ─────────────────────────────────────────────────────────────
# Scenario 1: tank 96% → motor OFF (safety rule)
# ─────────────────────────────────────────────────────────────

def test_scenario_1_tank_full_motor_off():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_water_motor_tank_full",
        rule_type=RuleType.SAFETY,
        trigger_field="tank_level_percent",
        trigger_op="gte",
        trigger_value=95,
        action_type=ActionType.DEVICE_COMMAND,
        command="turn_off",
    )
    event = make_event(payload={"tank_level_percent": 96, "state": "on"})

    result = evaluator.evaluate(event, {}, rule)

    assert result.match is True
    assert result.escalate_to_bedrock is False
    assert len(result.actions) == 1
    assert result.actions[0].command == "turn_off"


# ─────────────────────────────────────────────────────────────
# Scenario 2: geyser 21min → reminder (safety timeout)
# ─────────────────────────────────────────────────────────────

def test_scenario_2_geyser_timeout_reminder():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_geyser_timeout",
        rule_type=RuleType.SAFETY,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        trigger_field="running_minutes",
        trigger_op="gte",
        trigger_value=20,
        action_type=ActionType.NOTIFICATION,
        command=None,
    )
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        device_id="dev_geyser_001",
        payload={"running_minutes": 21, "state": "on"},
    )

    result = evaluator.evaluate(event, {}, rule)

    assert result.match is True
    assert result.actions[0].type == ActionType.NOTIFICATION


# ─────────────────────────────────────────────────────────────
# Scenario 3: 3 whistles → timer start (fleet rule)
# ─────────────────────────────────────────────────────────────

def test_scenario_3_pressure_cooker_3_whistles():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_pressure_cooker_3_whistles",
        rule_type=RuleType.FLEET,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.PRESSURE_COOKER,
        trigger_field="whistle_count",
        trigger_op="eq",
        trigger_value=3,
        action_type=ActionType.TIMER_START,
        command=None,
    )
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.PRESSURE_COOKER,
        device_id="dev_pressure_cooker_001",
        payload={"whistle_count": 3, "state": "on"},
    )

    result = evaluator.evaluate(event, {}, rule)

    assert result.match is True
    assert result.actions[0].type == ActionType.TIMER_START


# ─────────────────────────────────────────────────────────────
# Scenario 4: Dadaji medicine at 20:45 → reminder (promoted pattern)
# ─────────────────────────────────────────────────────────────

def test_scenario_4_dadaji_medicine_reminder():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_dadaji_medicine_evening",
        rule_type=RuleType.PROMOTED_PATTERN,
        event_type=EventType.SCHEDULE_EVENT,
        device_type=None,
        trigger_field="schedule_id",
        trigger_op="eq",
        trigger_value="rtn_dadaji_evening_meds",
        action_type=ActionType.REMINDER,
        command=None,
    )
    event = make_event(
        event_type=EventType.SCHEDULE_EVENT,
        device_type=None,
        device_id=None,
        payload={"schedule_id": "rtn_dadaji_evening_meds", "time": "20:45"},
    )

    result = evaluator.evaluate(event, {}, rule)

    assert result.match is True
    assert result.actions[0].type == ActionType.REMINDER


# ─────────────────────────────────────────────────────────────
# Scenario 5: fridge door 6min → reminder (fleet default)
# ─────────────────────────────────────────────────────────────

def test_scenario_5_fridge_door_open_reminder():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_fridge_door_open",
        rule_type=RuleType.FLEET,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.SMART_FRIDGE,
        trigger_field="door_open_seconds",
        trigger_op="gte",
        trigger_value=300,
        action_type=ActionType.NOTIFICATION,
        command=None,
    )
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.SMART_FRIDGE,
        device_id="dev_fridge_001",
        payload={"door_open_seconds": 360, "state": "door_open"},
    )

    result = evaluator.evaluate(event, {}, rule)

    assert result.match is True
    assert result.actions[0].type == ActionType.NOTIFICATION


# ─────────────────────────────────────────────────────────────
# Scenario 6: quiet hours + loud TV → volume reduce (custom rule)
# ─────────────────────────────────────────────────────────────

def test_scenario_6_quiet_hours_loud_tv():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_quiet_hours_tv",
        rule_type=RuleType.CUSTOM,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.TELEVISION,
        trigger_field="volume_percent",
        trigger_op="gte",
        trigger_value=50,
        conditions=[
            RuleCondition(
                field="context.quiet_hours_active",
                op="eq",
                value=True,
            )
        ],
        action_type=ActionType.DEVICE_COMMAND,
        command="reduce_volume",
    )
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.TELEVISION,
        device_id="dev_tv_001",
        payload={"volume_percent": 65, "state": "on"},
    )
    context = {"quiet_hours_active": True}

    result = evaluator.evaluate(event, context, rule)

    assert result.match is True
    assert result.actions[0].command == "reduce_volume"


# ─────────────────────────────────────────────────────────────
# Scenario 7: health vs fleet conflict → health wins
# ─────────────────────────────────────────────────────────────

def test_scenario_7_health_beats_fleet():
    resolver = ConflictResolver()
    evaluator = RuleEvaluationEngine()

    fleet_rule = make_rule(
        rule_id="rl_fleet_geyser",
        rule_type=RuleType.FLEET,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        trigger_field="running_minutes",
        trigger_op="gte",
        trigger_value=20,
        action_type=ActionType.NOTIFICATION,
        command=None,
    )
    health_rule = make_rule(
        rule_id="rl_health_geyser_dadaji",
        rule_type=RuleType.HEALTH,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        trigger_field="running_minutes",
        trigger_op="gte",
        trigger_value=20,
        action_type=ActionType.DEVICE_COMMAND,
        command="turn_off",
    )
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        device_id="dev_geyser_001",
        payload={"running_minutes": 25},
    )

    fleet_result = evaluator.evaluate(event, {}, fleet_rule)
    health_result = evaluator.evaluate(event, {}, health_rule)

    assert fleet_result.match is True
    assert health_result.match is True

    winners = resolver.resolve([(fleet_rule, fleet_result), (health_rule, health_result)])
    winner_ids = {r.rule_id for r, _ in winners}

    assert "rl_health_geyser_dadaji" in winner_ids
    assert "rl_fleet_geyser" not in winner_ids


# ─────────────────────────────────────────────────────────────
# Scenario 8: fleet vs custom geyser → custom wins (temp < 15°C)
# ─────────────────────────────────────────────────────────────

def test_scenario_8_custom_beats_fleet():
    resolver = ConflictResolver()
    evaluator = RuleEvaluationEngine()

    fleet_rule = make_rule(
        rule_id="rl_fleet_geyser_timeout",
        rule_type=RuleType.FLEET,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        trigger_field="running_minutes",
        trigger_op="gte",
        trigger_value=30,
        action_type=ActionType.NOTIFICATION,
        command=None,
    )
    custom_rule = make_rule(
        rule_id="rl_custom_geyser_winter",
        rule_type=RuleType.CUSTOM,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        trigger_field="running_minutes",
        trigger_op="gte",
        trigger_value=30,
        conditions=[
            RuleCondition(
                field="temperature_c",
                op="lt",
                value=15,
                on_fail="skip",
            )
        ],
        action_type=ActionType.NOTIFICATION,
        command=None,
    )
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        device_id="dev_geyser_001",
        payload={"running_minutes": 35, "temperature_c": 10},
    )

    fleet_result = evaluator.evaluate(event, {}, fleet_rule)
    custom_result = evaluator.evaluate(event, {}, custom_rule)

    assert fleet_result.match is True
    assert custom_result.match is True

    winners = resolver.resolve([(fleet_rule, fleet_result), (custom_rule, custom_result)])
    winner_ids = {r.rule_id for r, _ in winners}

    assert "rl_custom_geyser_winter" in winner_ids
    assert "rl_fleet_geyser_timeout" not in winner_ids


# ─────────────────────────────────────────────────────────────
# Scenario 9: on_fail escalate_to_bedrock → escalate flag set
# ─────────────────────────────────────────────────────────────

def test_scenario_9_on_fail_escalate_to_bedrock():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_health_complex",
        rule_type=RuleType.HEALTH,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        trigger_field="running_minutes",
        trigger_op="gte",
        trigger_value=20,
        conditions=[
            RuleCondition(
                field="context.health_condition_active",
                op="eq",
                value=True,
                on_fail="escalate_to_bedrock",
            )
        ],
        action_type=ActionType.NOTIFICATION,
        command=None,
    )
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.GEYSER,
        device_id="dev_geyser_001",
        payload={"running_minutes": 25},
    )
    # context.health_condition_active is missing → on_fail kicks in
    context = {}

    result = evaluator.evaluate(event, context, rule)

    assert result.match is False
    assert result.escalate_to_bedrock is True


# ─────────────────────────────────────────────────────────────
# Scenario 10: idempotency window active → action suppressed
# ─────────────────────────────────────────────────────────────

def test_scenario_10_idempotency_suppresses_duplicate():
    evaluator = RuleEvaluationEngine()
    rule = make_rule(
        rule_id="rl_idem_test",
        rule_type=RuleType.SAFETY,
        trigger_field="tank_level_percent",
        trigger_op="gte",
        trigger_value=90,
        action_type=ActionType.DEVICE_COMMAND,
        command="turn_off",
        idempotency_window_secs=300,
    )
    event = make_event(payload={"tank_level_percent": 96, "state": "on"})

    # First call — should fire
    evaluator._idempotency_cache.clear()
    first = evaluator.evaluate(event, {}, rule)
    assert first.match is True

    # Manually inject expiry in the future to simulate active window
    idem_key = evaluator._idempotency_key(HH_ID, rule.rule_id)
    evaluator._idempotency_cache[idem_key] = time.time() + 3600

    # Second call — should be suppressed
    second = evaluator.evaluate(event, {}, rule)
    assert second.match is False
    assert "Idempotency" in (second.reason or "")


# ─────────────────────────────────────────────────────────────
# Bonus: safety rules survive conflict resolution (never suppressed)
# ─────────────────────────────────────────────────────────────

def test_safety_rules_never_suppressed():
    resolver = ConflictResolver()
    evaluator = RuleEvaluationEngine()

    safety_rule = make_rule(
        rule_id="rl_safety_motor",
        rule_type=RuleType.SAFETY,
        trigger_field="tank_level_percent",
        trigger_op="gte",
        trigger_value=95,
        action_type=ActionType.DEVICE_COMMAND,
        command="turn_off",
    )
    custom_rule = make_rule(
        rule_id="rl_custom_motor",
        rule_type=RuleType.CUSTOM,
        trigger_field="tank_level_percent",
        trigger_op="gte",
        trigger_value=95,
        action_type=ActionType.NOTIFICATION,
        command=None,
    )
    event = make_event(payload={"tank_level_percent": 98})

    safety_result = evaluator.evaluate(event, {}, safety_rule)
    custom_result = evaluator.evaluate(event, {}, custom_rule)

    winners = resolver.resolve([(safety_rule, safety_result), (custom_rule, custom_result)])
    winner_ids = {r.rule_id for r, _ in winners}

    # Both safety AND the custom winner should be present
    assert "rl_safety_motor" in winner_ids
    assert len(winners) >= 1


# ─────────────────────────────────────────────────────────────
# Defensive tests — catching the class-variable idempotency bug
# ─────────────────────────────────────────────────────────────

def test_two_evaluator_instances_do_not_share_idempotency_cache():
    """
    RuleEvaluationEngine._idempotency_cache must be instance-level, not class-level.
    If it were class-level, evaluator_a firing a rule would suppress evaluator_b
    from firing the same rule within the TTL window.
    This was the exact bug that caused engine.run() to return 0 actions in production
    while all 11 unit tests still passed (tests use different rule_ids per scenario).
    """
    rule = make_rule(
        rule_id="rl_shared_cache_test",
        rule_type=RuleType.SAFETY,
        trigger_field="tank_level_percent",
        trigger_op="gte",
        trigger_value=90,
        action_type=ActionType.DEVICE_COMMAND,
        command="turn_off",
        idempotency_window_secs=300,
    )
    event = make_event(payload={"tank_level_percent": 96})

    evaluator_a = RuleEvaluationEngine()
    evaluator_b = RuleEvaluationEngine()

    # evaluator_a fires first — marks the key
    result_a = evaluator_a.evaluate(event, {}, rule)
    assert result_a.match is True, "First evaluator should fire"

    # evaluator_b is a different instance — must NOT see evaluator_a's cache
    result_b = evaluator_b.evaluate(event, {}, rule)
    assert result_b.match is True, (
        "Second evaluator instance must fire independently. "
        "If this fails, _idempotency_cache is a class variable (shared state bug)."
    )


def test_engine_run_returns_action_for_water_motor_tank_full():
    """
    Integration test: engine.run() must produce at least 1 action for the
    rl_water_motor_tank_full rule when tank_level_percent=96.
    This test catches the class-variable idempotency bug at the engine level.
    Previously: 11/11 unit tests passed but this exact scenario returned 0 actions.
    """
    from engines.rule_engine import RuleEngine

    engine = RuleEngine()
    engine._registry.load("hh_xk92p_sharma")

    event = make_event(payload={"tank_level_percent": 96, "state": "on"})

    actions = engine.run(event)

    assert len(actions) >= 1, f"Expected at least 1 action, got {len(actions)}"
    action_types = {a.action_type for a in actions}
    assert ActionType.DEVICE_COMMAND in action_types
    sources = {a.source for a in actions}
    assert ActionSource.RULE_ENGINE in sources
