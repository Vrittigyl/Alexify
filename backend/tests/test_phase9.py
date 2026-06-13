"""
tests/test_phase9.py
=====================
Unit + integration tests for Phase 9:
  - PresenceService (9.1)
  - ContextEngine (9.2)
  - EventBatcher (9.3)
  - ContextBuilder (9.4)
  - BedrockCircuitBreaker (9.5)
  - BedrockLayer mock (9.6)
  - PatternEngine (9.7)
  - MetricsService (9.8)

Run: pytest tests/test_phase9.py -v
"""

import time
import pytest
from schemas import NormalizedEvent
from schemas.enums import (
    CircuitState, ConfidenceBand, DeviceType, EventType, ImpactLevel, RouteDecision,
)
from schemas.intelligence import HouseholdContext, MemberPresence

HH_ID = "hh_xk92p_sharma"


def make_event(
    event_type=EventType.DEVICE_STATE,
    device_type=DeviceType.WATER_MOTOR,
    device_id="dev_water_motor_001",
    payload=None,
    impact_level=ImpactLevel.LOW,
) -> NormalizedEvent:
    return NormalizedEvent(
        household_id=HH_ID,
        event_type=event_type,
        device_type=device_type,
        device_id=device_id,
        payload=payload or {"tank_level_percent": 50},
        impact_level=impact_level,
    )


# ─────────────────────────────────────────────────────────────
# 9.1 PresenceService
# ─────────────────────────────────────────────────────────────

class TestPresenceService:
    def setup_method(self):
        from services.presence_service import PresenceService
        self.svc = PresenceService(ttl_secs=2)  # short TTL for tests

    def test_update_and_retrieve(self):
        self.svc.update(HH_ID, "mbr_dadaji_001", room_id="bedroom", is_home=True)
        assert self.svc.get_member_room(HH_ID, "mbr_dadaji_001") == "bedroom"
        assert self.svc.is_home(HH_ID, "mbr_dadaji_001") is True

    def test_get_all_returns_all_home_members(self):
        self.svc.update(HH_ID, "mbr_dadaji_001", is_home=True)
        self.svc.update(HH_ID, "mbr_rohan_005", is_home=True)
        records = self.svc.get_all(HH_ID)
        ids = {r.member_id for r in records}
        assert "mbr_dadaji_001" in ids
        assert "mbr_rohan_005" in ids

    def test_record_expires_after_ttl(self):
        self.svc.update(HH_ID, "mbr_mama_004", is_home=True)
        time.sleep(2.1)
        assert self.svc.is_home(HH_ID, "mbr_mama_004") is False
        assert self.svc.get_member_room(HH_ID, "mbr_mama_004") is None

    def test_mark_left_sets_not_home(self):
        self.svc.update(HH_ID, "mbr_papa_003", is_home=True)
        self.svc.mark_left(HH_ID, "mbr_papa_003")
        assert self.svc.is_home(HH_ID, "mbr_papa_003") is False

    def test_evict_expired_removes_stale(self):
        self.svc.update(HH_ID, "mbr_dadiji_002", is_home=True)
        time.sleep(2.1)
        removed = self.svc.evict_expired()
        assert removed >= 1

    def test_home_member_ids(self):
        svc2 = __import__("services.presence_service", fromlist=["PresenceService"]).PresenceService(ttl_secs=30)
        svc2.update(HH_ID, "mbr_dadaji_001", is_home=True)
        svc2.update(HH_ID, "mbr_rohan_005", is_home=False)
        home = svc2.get_home_member_ids(HH_ID)
        assert "mbr_dadaji_001" in home
        assert "mbr_rohan_005" not in home


# ─────────────────────────────────────────────────────────────
# 9.2 ContextEngine
# ─────────────────────────────────────────────────────────────

class TestContextEngine:
    def setup_method(self):
        from services.context_engine import ContextEngine
        from services.presence_service import PresenceService
        self.presence = PresenceService(ttl_secs=60)
        self.presence.update(HH_ID, "mbr_dadaji_001", room_id="bedroom", is_home=True)
        self.engine = ContextEngine(presence=self.presence)

    def test_build_returns_household_context(self):
        event = make_event()
        ctx = self.engine.build(event, HH_ID)
        assert ctx.household_id == HH_ID

    def test_time_of_day_is_set(self):
        event = make_event()
        ctx = self.engine.build(event, HH_ID)
        assert ctx.time_of_day in (
            "early_morning", "morning", "midday", "afternoon",
            "evening", "night", "late_night"
        )

    def test_members_presence_reflects_service(self):
        event = make_event()
        ctx = self.engine.build(event, HH_ID)
        ids = {m.member_id for m in ctx.members_presence}
        assert "mbr_dadaji_001" in ids

    def test_context_has_ist_time(self):
        event = make_event()
        ctx = self.engine.build(event, HH_ID)
        assert ctx.ist_time is not None
        assert ":" in ctx.ist_time  # HH:MM format

    def test_context_has_day_of_week(self):
        from services.context_engine import _DAY_NAMES
        event = make_event()
        ctx = self.engine.build(event, HH_ID)
        assert ctx.day_of_week in _DAY_NAMES


# ─────────────────────────────────────────────────────────────
# 9.3 EventBatcher
# ─────────────────────────────────────────────────────────────

class TestEventBatcher:
    def setup_method(self):
        from services.event_batcher import EventBatcher
        self.batcher = EventBatcher(window_mins=1, max_batch_size=5)

    def test_add_returns_true_for_new_event(self):
        event = make_event()
        result = self.batcher.add(event)
        assert result is True
        assert self.batcher.batch_size(HH_ID) == 1

    def test_dedup_suppresses_same_device_event_type(self):
        e1 = make_event(device_id="dev_motor_001")
        e2 = make_event(device_id="dev_motor_001")  # same device+type within 2min
        self.batcher.add(e1)
        result = self.batcher.add(e2)
        assert result is False  # deduped
        assert self.batcher.batch_size(HH_ID) == 1

    def test_different_device_not_deduped(self):
        e1 = make_event(device_id="dev_motor_001")
        e2 = make_event(device_id="dev_motor_002")
        self.batcher.add(e1)
        result = self.batcher.add(e2)
        assert result is True

    def test_flush_returns_events_and_clears(self):
        e1 = make_event(device_id="dev_a_001")
        e2 = make_event(device_id="dev_b_001", device_type=DeviceType.GEYSER)
        self.batcher.add(e1)
        self.batcher.add(e2)
        flushed = self.batcher.flush(HH_ID)
        assert len(flushed) == 2
        assert self.batcher.batch_size(HH_ID) == 0

    def test_should_flush_on_critical(self):
        event = make_event(impact_level=ImpactLevel.CRITICAL)
        self.batcher.add(event)
        assert self.batcher.should_flush(HH_ID, event) is True

    def test_should_flush_on_max_size(self):
        for i in range(5):
            e = make_event(device_id=f"dev_{i:03d}", device_type=DeviceType.LIGHT)
            self.batcher.add(e)
        event = make_event(device_id="dev_extra_001", device_type=DeviceType.AC)
        assert self.batcher.should_flush(HH_ID, event) is True

    def test_get_batch_does_not_clear(self):
        self.batcher.add(make_event(device_id="dev_x_001"))
        batch = self.batcher.get_batch(HH_ID)
        assert len(batch) == 1
        assert self.batcher.batch_size(HH_ID) == 1  # still there


# ─────────────────────────────────────────────────────────────
# 9.4 ContextBuilder
# ─────────────────────────────────────────────────────────────

class TestContextBuilder:
    def setup_method(self):
        from services.bedrock_layer import ContextBuilder
        from services.presence_service import PresenceService
        self.builder = ContextBuilder()
        self.ctx = HouseholdContext(
            household_id=HH_ID,
            members_presence=[
                MemberPresence(member_id="mbr_dadaji_001", room_id="bedroom", is_home=True)
            ],
            device_states={"dev_water_motor_001": {"state": "on", "tank_level_percent": 96}},
            active_life_events=[{"event": "board_exams"}],
            time_of_day="evening",
            ist_time="20:30",
            day_of_week="Monday",
        )

    def test_build_returns_bedrock_context(self):
        from schemas.bedrock import BedrockContext
        events = [make_event()]
        bc = self.builder.build_bedrock_context(events, self.ctx)
        assert isinstance(bc, BedrockContext)
        assert bc.household_id == HH_ID

    def test_estimated_tokens_set(self):
        events = [make_event()]
        bc = self.builder.build_bedrock_context(events, self.ctx)
        assert bc.estimated_tokens is not None
        assert bc.estimated_tokens > 0

    def test_token_range_reasonable(self):
        events = [make_event()]
        bc = self.builder.build_bedrock_context(events, self.ctx)
        # Should be in 200-3000 range for typical context
        assert 100 <= bc.estimated_tokens <= 3000

    def test_rule_engine_already_handled_passed(self):
        events = [make_event()]
        bc = self.builder.build_bedrock_context(
            events, self.ctx,
            rule_engine_already_handled=["rl_water_motor_tank_full"]
        )
        assert "rl_water_motor_tank_full" in bc.rule_engine_already_handled

    def test_device_states_capped_at_10(self):
        # Context with 15 device states
        big_ctx = HouseholdContext(
            household_id=HH_ID,
            device_states={f"dev_{i:03d}": {"state": "on"} for i in range(15)},
        )
        events = [make_event()]
        bc = self.builder.build_bedrock_context(events, big_ctx)
        assert len(bc.device_states) <= 10


# ─────────────────────────────────────────────────────────────
# 9.5 BedrockCircuitBreaker
# ─────────────────────────────────────────────────────────────

class TestBedrockCircuitBreaker:
    def setup_method(self):
        from services.bedrock_layer import BedrockCircuitBreaker
        # Use short thresholds for testing
        self.cb = BedrockCircuitBreaker()
        self.cb._failure_threshold = 3
        self.cb._window_secs = 5
        self.cb._probe_interval = 1

    def test_initial_state_closed(self):
        assert self.cb.state == CircuitState.CLOSED
        assert self.cb.is_open() is False

    def test_opens_after_threshold_failures(self):
        for _ in range(3):
            self.cb.record_failure(HH_ID)
        assert self.cb.state == CircuitState.OPEN
        assert self.cb.is_open() is True

    def test_success_closes_circuit(self):
        for _ in range(3):
            self.cb.record_failure(HH_ID)
        assert self.cb.state == CircuitState.OPEN
        self.cb.record_success()
        assert self.cb.state == CircuitState.CLOSED
        assert self.cb.is_open() is False

    def test_transitions_to_half_open_after_probe_interval(self):
        for _ in range(3):
            self.cb.record_failure(HH_ID)
        assert self.cb.state == CircuitState.OPEN
        time.sleep(1.1)  # wait for probe_interval=1s
        # is_open() transitions to HALF_OPEN and allows through
        result = self.cb.is_open()
        assert result is False
        assert self.cb.state == CircuitState.HALF_OPEN

    def test_failure_window_resets(self):
        # Short window — after reset, failures start fresh
        self.cb._failure_count = 2
        self.cb._window_start = time.monotonic() - 10  # expired window
        self.cb.record_failure(HH_ID)
        # Window reset → count=1, not 3 → still CLOSED
        assert self.cb.state == CircuitState.CLOSED

    def test_get_state_dict(self):
        d = self.cb.get_state_dict()
        assert "state" in d
        assert "failure_count" in d


# ─────────────────────────────────────────────────────────────
# 9.6 BedrockLayer (mock mode)
# ─────────────────────────────────────────────────────────────

class TestBedrockLayerMock:
    def setup_method(self):
        from services.bedrock_layer import BedrockLayer, ContextBuilder
        self.layer = BedrockLayer(mock_mode=True)
        self.builder = ContextBuilder()
        self.ctx = HouseholdContext(
            household_id=HH_ID,
            time_of_day="evening",
            ist_time="19:45",
            day_of_week="Monday",
        )

    def _build_ctx(self, event_type: str):
        from schemas.bedrock import BedrockContext
        return BedrockContext(
            household_id=HH_ID,
            events=[{"event_type": event_type, "payload": {}}],
            estimated_tokens=1100,
        )

    def test_mock_returns_bedrock_response(self):
        from schemas.bedrock import BedrockResponse
        bc = self._build_ctx("guest_arrival")
        resp = self.layer.invoke(bc, HH_ID)
        assert isinstance(resp, BedrockResponse)

    def test_mock_guest_arrival_has_actions(self):
        bc = self._build_ctx("guest_arrival")
        resp = self.layer.invoke(bc, HH_ID)
        assert len(resp.actions) >= 1

    def test_mock_life_event_has_actions(self):
        bc = self._build_ctx("life_event")
        resp = self.layer.invoke(bc, HH_ID)
        assert len(resp.actions) >= 1

    def test_mock_sets_confidence(self):
        bc = self._build_ctx("guest_arrival")
        resp = self.layer.invoke(bc, HH_ID)
        assert 0.0 <= resp.confidence <= 1.0

    def test_mock_tracks_tokens(self):
        bc = self._build_ctx("life_event")
        resp = self.layer.invoke(bc, HH_ID)
        assert resp.total_tokens > 0

    def test_circuit_open_returns_empty_response(self):
        from services.bedrock_layer import BedrockCircuitBreaker
        cb = BedrockCircuitBreaker()
        cb._failure_threshold = 1
        cb.record_failure(HH_ID)
        layer = __import__("services.bedrock_layer", fromlist=["BedrockLayer"]).BedrockLayer(circuit_breaker=cb, mock_mode=True)
        bc = self._build_ctx("guest_arrival")
        resp = layer.invoke(bc, HH_ID)
        assert len(resp.actions) == 0
        assert resp.confidence == 0.0

    def test_circuit_records_success_on_good_call(self):
        bc = self._build_ctx("guest_arrival")
        self.layer.invoke(bc, HH_ID)
        assert self.layer._cb.state == CircuitState.CLOSED


# ─────────────────────────────────────────────────────────────
# 9.7 PatternEngine
# ─────────────────────────────────────────────────────────────

class TestPatternEngine:
    def setup_method(self):
        from services.pattern_engine import PatternEngine
        self.engine = PatternEngine()

    def test_load_returns_pattern_records(self):
        from schemas.intelligence import PatternRecord
        patterns = self.engine.load(HH_ID)
        assert isinstance(patterns, list)
        assert all(isinstance(p, PatternRecord) for p in patterns)

    def test_load_promoted_returns_only_promoted(self):
        patterns = self.engine.load_promoted(HH_ID)
        for p in patterns:
            assert p.confidence_band == ConfidenceBand.PROMOTED

    def test_promote_if_eligible_returns_list(self):
        promoted = self.engine.promote_if_eligible(HH_ID)
        assert isinstance(promoted, list)

    def test_ingest_suggestions_creates_observing_patterns(self):
        suggestions = [
            {
                "pattern_id": "ptn_test_guest_lights",
                "description": "Test: warm lights for guests",
                "confidence": 0.0,
                "event_type": "guest_arrival",
            }
        ]
        upserted = self.engine.ingest_suggestions(HH_ID, suggestions)
        assert "ptn_test_guest_lights" in upserted

    def test_record_miss_increments_counter(self):
        patterns = self.engine.load(HH_ID)
        if not patterns:
            pytest.skip("No patterns in DynamoDB to test miss recording")
        p = patterns[0]
        original_misses = p.consecutive_misses
        updated = self.engine.record_miss(HH_ID, p.pattern_id)
        assert updated is not None
        assert updated.consecutive_misses == original_misses + 1


# ─────────────────────────────────────────────────────────────
# 9.8 MetricsService
# ─────────────────────────────────────────────────────────────

class TestMetricsService:
    def setup_method(self):
        from services.metrics_service import MetricsService
        self.svc = MetricsService(HH_ID)

    def test_initial_state_zero(self):
        m = self.svc.get_dashboard_metrics()
        assert m.total_events_processed == 0
        assert m.rule_engine_calls == 0
        assert m.bedrock_calls == 0

    def test_record_rule_engine_increments(self):
        self.svc.record_rule_engine(latency_ms=12.5)
        m = self.svc.get_dashboard_metrics()
        assert m.total_events_processed == 1
        assert m.rule_engine_calls == 1
        assert m.avg_rule_engine_latency_ms == 12.5

    def test_record_bedrock_increments(self):
        self.svc.record_bedrock(latency_ms=450.0, tokens=1250)
        m = self.svc.get_dashboard_metrics()
        assert m.bedrock_calls == 1
        assert m.total_bedrock_tokens == 1250
        assert m.avg_tokens_per_call == 1250.0

    def test_record_suppressed(self):
        self.svc.record_suppressed()
        m = self.svc.get_dashboard_metrics()
        assert m.suppressed_events == 1
        assert m.total_events_processed == 1

    def test_rule_engine_percentage_calculation(self):
        self.svc.record_rule_engine(latency_ms=10)
        self.svc.record_rule_engine(latency_ms=10)
        self.svc.record_suppressed()
        m = self.svc.get_dashboard_metrics()
        # 2 RE out of 3 total = 66.7%
        assert abs(m.rule_engine_percentage - 66.7) < 0.1

    def test_token_savings_percentage(self):
        # v1=3800 tokens, v2=1250 → savings = (3800-1250)/3800 = 67.1%
        self.svc.record_bedrock(latency_ms=300, tokens=1250)
        m = self.svc.get_dashboard_metrics()
        assert m.token_savings_percentage > 60.0

    def test_p99_latency(self):
        for i in range(100):
            self.svc.record_rule_engine(latency_ms=float(i))
        m = self.svc.get_dashboard_metrics()
        assert m.p99_rule_engine_latency_ms >= 98.0

    def test_pattern_count_update(self):
        self.svc.update_pattern_counts(active=5, promoted=3, learning=2, observing=0)
        m = self.svc.get_dashboard_metrics()
        assert m.active_patterns == 5
        assert m.promoted_patterns == 3

    def test_dashboard_metrics_household_id(self):
        m = self.svc.get_dashboard_metrics()
        assert m.household_id == HH_ID
