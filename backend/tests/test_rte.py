"""
tests/test_rte.py
13 routing scenarios from the v2.0 taxonomy table.
Run: pytest tests/test_rte.py -v

Scenario map:
  1.  water_motor tank 96%            -> RULE_ENGINE / Stage1
  2.  geyser 31min running            -> RULE_ENGINE / Stage1
  3.  pressure_cooker 3 whistles      -> RULE_ENGINE / Stage1
  4.  Dadaji medicine schedule        -> RULE_ENGINE / Stage2 (promoted pattern)
  5.  fridge normal (door closed)     -> SUPPRESS / Stage3
  6.  TV normal low volume            -> SUPPRESS / Stage3
  7.  board_exam life event           -> BEDROCK / Stage3 (score >= threshold)
  8.  guest_arrival                   -> BEDROCK / Stage3 (AI_REQUIRED = +100)
  9.  festival_declaration            -> BEDROCK / Stage3 (AI_REQUIRED = +100)
  10. health_emergency                -> BEDROCK / Stage3 (AI_REQUIRED = +100)
  11. requires_ai=True on event       -> BEDROCK / Stage3
  12. multiple members + life event   -> BEDROCK / Stage3 (score 210)
  13. Stage1 miss + Stage2 miss + low score -> SUPPRESS / Stage3
"""

import pytest
from schemas import NormalizedEvent
from schemas.enums import DeviceType, EventType, RouteDecision
from engines.rte import (
    RTE,
    Stage1_RuleRegistryCheck,
    Stage2_PatternPromotionCheck,
    Stage3_ComplexityScorer,
    Stage4_Default,
)
from engines.rule_engine import RuleRegistry

HH_ID = "hh_xk92p_sharma"


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def loaded_registry():
    """Registry pre-loaded with live DynamoDB rules."""
    r = RuleRegistry()
    r.load(HH_ID)
    return r


@pytest.fixture(scope="module")
def promoted_patterns():
    """PROMOTED patterns from DynamoDB."""
    from graph_repository import GraphRepository
    repo = GraphRepository()
    return repo.get_patterns(HH_ID, band="PROMOTED")


@pytest.fixture(scope="module")
def rte(loaded_registry, promoted_patterns):
    return RTE(rule_registry=loaded_registry, promoted_patterns=promoted_patterns)


def make_event(
    event_type=EventType.DEVICE_STATE,
    device_type=DeviceType.WATER_MOTOR,
    device_id="dev_water_motor_001",
    payload=None,
    requires_ai=False,
    affected_member_ids=None,
) -> NormalizedEvent:
    return NormalizedEvent(
        household_id=HH_ID,
        event_type=event_type,
        device_type=device_type,
        device_id=device_id,
        payload=payload or {},
        requires_ai=requires_ai,
        affected_member_ids=affected_member_ids or [],
    )


# ─────────────────────────────────────────────────────────────
# Scenario 1: water_motor tank 96% -> RULE_ENGINE / Stage1
# ─────────────────────────────────────────────────────────────

def test_s1_water_motor_tank_full_routes_rule_engine(rte):
    event = make_event(
        device_type=DeviceType.WATER_MOTOR,
        payload={"tank_level_percent": 96, "state": "on"},
    )
    decision = rte.classify(event)
    assert decision.route == RouteDecision.RULE_ENGINE
    assert decision.stage_decided == 1
    # rule_matched is whichever candidate is returned first from the registry
    # (dict order is insertion-order in Python 3.7+, but not semantically guaranteed
    # across DynamoDB scans). Assert a valid rule was matched, not a specific one.
    assert decision.rule_matched is not None


# ─────────────────────────────────────────────────────────────
# Scenario 2: geyser 31min -> RULE_ENGINE / Stage1
# ─────────────────────────────────────────────────────────────

def test_s2_geyser_timeout_routes_rule_engine(rte):
    event = make_event(
        device_type=DeviceType.GEYSER,
        device_id="dev_geyser_001",
        payload={"running_minutes": 31, "state": "on"},
    )
    decision = rte.classify(event)
    assert decision.route == RouteDecision.RULE_ENGINE
    assert decision.stage_decided == 1


# ─────────────────────────────────────────────────────────────
# Scenario 3: pressure_cooker 3 whistles -> RULE_ENGINE / Stage1
# ─────────────────────────────────────────────────────────────

def test_s3_pressure_cooker_routes_rule_engine(rte):
    """whistle_count=5 hits the rl_pressure_cooker_whistle_limit threshold (eq 5)."""
    event = make_event(
        device_type=DeviceType.PRESSURE_COOKER,
        device_id="dev_pressure_cooker_001",
        payload={"whistle_count": 5, "state": "on", "temperature_c": 121},
    )
    decision = rte.classify(event)
    assert decision.route == RouteDecision.RULE_ENGINE
    assert decision.stage_decided == 1
    assert decision.rule_matched == "rl_pressure_cooker_whistle_limit"


def test_s3b_pressure_cooker_3_whistles_suppressed(rte):
    """whistle_count=3 does NOT match the rule (threshold=5) — Stage1 field-check suppresses."""
    event = make_event(
        device_type=DeviceType.PRESSURE_COOKER,
        device_id="dev_pressure_cooker_001",
        payload={"whistle_count": 3, "state": "on"},
    )
    decision = rte.classify(event)
    assert decision.route == RouteDecision.SUPPRESS



# ─────────────────────────────────────────────────────────────
# Scenario 4: Dadaji medicine schedule -> RULE_ENGINE / Stage2
# ─────────────────────────────────────────────────────────────

def test_s4_dadaji_medicine_routes_via_promoted_pattern(promoted_patterns):
    """
    Stage2 should catch the promoted pattern for Dadaji's medicine schedule.
    Promoted patterns use event_type=routine_trigger (verified from DynamoDB).
    The event must use the same type so Stage2 matching works.
    """
    stage2 = Stage2_PatternPromotionCheck(promoted_patterns)

    # Dadaji's medicine patterns store event_type='routine_trigger'
    event = make_event(
        event_type=EventType.ROUTINE_TRIGGER,
        device_type=None,
        device_id=None,
        payload={"routine_id": "rtn_dadaji_evening_meds"},
    )

    route, pattern_id = stage2.check(event)
    assert route == RouteDecision.RULE_ENGINE, (
        f"Expected RULE_ENGINE from Stage2 promoted pattern match, got {route}. "
        f"Promoted patterns: {[p['pattern_id'] for p in promoted_patterns]}"
    )
    assert pattern_id is not None


# ─────────────────────────────────────────────────────────────
# Scenario 5: fridge normal (door closed) -> SUPPRESS / Stage3
# ─────────────────────────────────────────────────────────────

def test_s5_fridge_normal_suppressed():
    """No rule matches normal fridge state, score below threshold."""
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        device_type=DeviceType.SMART_FRIDGE,
        device_id="dev_fridge_001",
        payload={"state": "closed", "door_open_seconds": 0, "temperature_c": 4.0},
    )
    route, score, breakdown = scorer.check(event, context={})
    assert route == RouteDecision.SUPPRESS
    assert score < 40


# ─────────────────────────────────────────────────────────────
# Scenario 6: TV normal low volume -> SUPPRESS / Stage3
# ─────────────────────────────────────────────────────────────

def test_s6_tv_normal_suppressed():
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        device_type=DeviceType.TELEVISION,
        device_id="dev_tv_001",
        payload={"state": "on", "volume_percent": 25, "channel": "DD News"},
    )
    route, score, breakdown = scorer.check(event, context={})
    assert route == RouteDecision.SUPPRESS
    assert score < 40


# ─────────────────────────────────────────────────────────────
# Scenario 7: board_exam life event -> BEDROCK / Stage3
# ─────────────────────────────────────────────────────────────

def test_s7_board_exam_routes_bedrock():
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        event_type=EventType.LIFE_EVENT,
        device_type=None,
        device_id=None,
        payload={"life_event_id": "le_rohan_boards"},
        affected_member_ids=[
            "mbr_rohan_005", "mbr_mama_004", "mbr_papa_003",
            "mbr_dadaji_001", "mbr_dadiji_002",
        ],
    )
    context = {
        "active_life_events": [{"event": "le_rohan_boards"}],
        "health_constraints": ["hypertension", "diabetes", "arthritis"],
    }
    route, score, breakdown = scorer.check(event, context)
    assert route == RouteDecision.BEDROCK
    # ai_required=100 + life_events=25 + health=90 + members=75 = 290
    assert score >= 40
    assert "ai_required" in breakdown


# ─────────────────────────────────────────────────────────────
# Scenario 8: guest_arrival -> BEDROCK / Stage3 (AI_REQUIRED)
# ─────────────────────────────────────────────────────────────

def test_s8_guest_arrival_routes_bedrock(rte):
    event = make_event(
        event_type=EventType.GUEST_ARRIVAL,
        device_type=None,
        device_id=None,
        payload={"guest_count": 5, "relation": "extended_family"},
    )
    decision = rte.classify(event)
    assert decision.route == RouteDecision.BEDROCK
    # guest_arrival is in AI_REQUIRED_EVENT_TYPES → ai_required score applied


# ─────────────────────────────────────────────────────────────
# Scenario 9: festival_declaration -> BEDROCK / Stage3 (AI_REQUIRED)
# ─────────────────────────────────────────────────────────────

def test_s9_festival_declaration_routes_bedrock():
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        event_type=EventType.FESTIVAL_DECLARATION,
        device_type=None,
        device_id=None,
        payload={"festival": "Diwali"},
    )
    route, score, breakdown = scorer.check(event, context={})
    assert route == RouteDecision.BEDROCK
    assert score >= 100
    assert breakdown.get("ai_required", 0) == 100


# ─────────────────────────────────────────────────────────────
# Scenario 10: health_emergency -> BEDROCK (AI_REQUIRED)
# ─────────────────────────────────────────────────────────────

def test_s10_health_emergency_routes_bedrock():
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        event_type=EventType.HEALTH_EMERGENCY,
        device_type=None,
        device_id=None,
        payload={"member_id": "mbr_dadaji_001", "symptom": "chest_pain"},
    )
    route, score, breakdown = scorer.check(event, context={})
    assert route == RouteDecision.BEDROCK
    assert score >= 100


# ─────────────────────────────────────────────────────────────
# Scenario 11: requires_ai=True flag on event -> BEDROCK
# ─────────────────────────────────────────────────────────────

def test_s11_requires_ai_flag_routes_bedrock():
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.SMART_FRIDGE,
        payload={"state": "closed"},
        requires_ai=True,   # explicit flag
    )
    route, score, breakdown = scorer.check(event, context={})
    assert route == RouteDecision.BEDROCK
    assert breakdown.get("ai_required", 0) == 100


# ─────────────────────────────────────────────────────────────
# Scenario 12: multiple members + life event -> BEDROCK score 210
# ─────────────────────────────────────────────────────────────

def test_s12_high_complexity_score_routes_bedrock():
    """
    life_event type (+100) + 3 health constraints (+90) + 3 life events in context (+75)
    + 5 members (+75) = 340. Well above threshold=40.
    """
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        event_type=EventType.LIFE_EVENT,
        device_type=None,
        device_id=None,
        payload={},
        affected_member_ids=["mbr_dadaji_001", "mbr_dadiji_002", "mbr_mama_004",
                              "mbr_papa_003", "mbr_rohan_005"],
    )
    context = {
        "active_life_events": [{"id": "le_1"}, {"id": "le_2"}, {"id": "le_3"}],
        "health_constraints": ["hypertension", "diabetes", "arthritis"],
    }
    route, score, breakdown = scorer.check(event, context)
    assert route == RouteDecision.BEDROCK
    assert score >= 210
    assert breakdown["members"] == 5 * 15
    assert breakdown["life_events"] == 3 * 25
    assert breakdown["health_constraints"] == 3 * 30


# ─────────────────────────────────────────────────────────────
# Scenario 13: Stage1 miss + Stage2 miss + low score -> SUPPRESS
# ─────────────────────────────────────────────────────────────

def test_s13_no_match_low_score_suppressed():
    """
    Event with an unregistered device type, no promoted patterns match,
    and empty context → Stage3 score = 0 → SUPPRESS.
    """
    # Stage1: empty registry (no rules)
    empty_registry = RuleRegistry()
    empty_registry._cache = {}
    empty_registry._raw_rules = []
    empty_registry._last_load = 9999999999.0

    rte = RTE(rule_registry=empty_registry, promoted_patterns=[])

    event = make_event(
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.LIGHT,
        device_id="dev_light_001",
        payload={"state": "on", "brightness": 50},
    )
    decision = rte.classify(event)
    assert decision.route == RouteDecision.SUPPRESS
    assert decision.complexity_score == 0


# ─────────────────────────────────────────────────────────────
# RTEDecision structure tests
# ─────────────────────────────────────────────────────────────

def test_rte_decision_has_required_fields(rte):
    event = make_event(payload={"tank_level_percent": 96})
    decision = rte.classify(event)
    assert decision.event_id == event.event_id
    assert decision.household_id == HH_ID
    assert decision.route in RouteDecision.__members__.values()
    assert decision.stage_decided in (1, 2, 3, 4)
    assert decision.latency_ms >= 0


def test_stage4_default_always_suppresses():
    stage4 = Stage4_Default()
    assert stage4.check() == RouteDecision.SUPPRESS


def test_complexity_score_breakdown_present_for_bedrock_decisions():
    scorer = Stage3_ComplexityScorer()
    event = make_event(
        event_type=EventType.GUEST_ARRIVAL,
        device_type=None,
        device_id=None,
    )
    route, score, breakdown = scorer.check(event, {})
    assert route == RouteDecision.BEDROCK
    assert "ai_required" in breakdown
    assert breakdown["total"] == score
    assert "threshold" in breakdown
