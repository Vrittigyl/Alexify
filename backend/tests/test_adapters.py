"""
tests/test_adapters.py
One test per adapter + dedup + registry + life event ingestion.
Run: pytest tests/test_adapters.py -v
"""

import pytest
from schemas import NormalizedEvent
from schemas.enums import DeviceType, EventType, ImpactLevel
from adapters.water_motor_adapter import WaterMotorAdapter
from adapters.geyser_adapter import GeyserAdapter
from adapters.pressure_cooker_adapter import PressureCookerAdapter
from adapters.television_adapter import TelevisionAdapter
from adapters.smart_fridge_adapter import SmartFridgeAdapter
from adapters.adapter_registry import get_adapter, registered_types
from engines.event_ingestion import ingest, ingest_life_event, _dedup_cache


HH_ID = "hh_xk92p_sharma"


# ─────────────────────────────────────────────────────────────
# Water Motor
# ─────────────────────────────────────────────────────────────

def test_water_motor_normal():
    adapter = WaterMotorAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "tank_level_percent": 40, "flow_rate_lpm": 18.0},
        household_id=HH_ID,
        device_id="dev_water_motor_001",
    )
    assert isinstance(event, NormalizedEvent)
    assert event.device_type == DeviceType.WATER_MOTOR
    assert event.event_type == EventType.DEVICE_STATE
    assert event.impact_level == ImpactLevel.LOW
    assert event.dedup_key is not None
    assert event.payload["tank_level_percent"] == 40


def test_water_motor_tank_full_impact():
    adapter = WaterMotorAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "tank_level_percent": 96, "flow_rate_lpm": 3.0},
        household_id=HH_ID,
        device_id="dev_water_motor_001",
    )
    assert event.impact_level == ImpactLevel.HIGH


# ─────────────────────────────────────────────────────────────
# Geyser
# ─────────────────────────────────────────────────────────────

def test_geyser_normal():
    adapter = GeyserAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "running_minutes": 10, "temperature_c": 55},
        household_id=HH_ID,
        device_id="dev_geyser_001",
    )
    assert isinstance(event, NormalizedEvent)
    assert event.device_type == DeviceType.GEYSER
    assert event.impact_level == ImpactLevel.LOW
    assert event.dedup_key is not None


def test_geyser_timeout_impact():
    adapter = GeyserAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "running_minutes": 31, "temperature_c": 70},
        household_id=HH_ID,
        device_id="dev_geyser_001",
    )
    assert event.impact_level == ImpactLevel.HIGH


def test_geyser_overheat_critical():
    adapter = GeyserAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "running_minutes": 15, "temperature_c": 85},
        household_id=HH_ID,
        device_id="dev_geyser_001",
    )
    assert event.impact_level == ImpactLevel.CRITICAL


# ─────────────────────────────────────────────────────────────
# Pressure Cooker
# ─────────────────────────────────────────────────────────────

def test_pressure_cooker_normal():
    adapter = PressureCookerAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "whistle_count": 2, "temperature_c": 100, "pressure_kpa": 120},
        household_id=HH_ID,
        device_id="dev_pressure_cooker_001",
    )
    assert isinstance(event, NormalizedEvent)
    assert event.device_type == DeviceType.PRESSURE_COOKER
    assert event.impact_level == ImpactLevel.LOW
    assert event.payload["whistle_count"] == 2
    assert event.dedup_key is not None


def test_pressure_cooker_5_whistles():
    adapter = PressureCookerAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "whistle_count": 5, "temperature_c": 121, "pressure_kpa": 150},
        household_id=HH_ID,
        device_id="dev_pressure_cooker_001",
    )
    assert event.impact_level == ImpactLevel.HIGH


# ─────────────────────────────────────────────────────────────
# Television
# ─────────────────────────────────────────────────────────────

def test_television_normal():
    adapter = TelevisionAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "volume_percent": 30, "channel": "DD News"},
        household_id=HH_ID,
        device_id="dev_tv_001",
    )
    assert isinstance(event, NormalizedEvent)
    assert event.device_type == DeviceType.TELEVISION
    assert event.impact_level == ImpactLevel.INFO
    assert event.dedup_key is not None


def test_television_loud_impact():
    adapter = TelevisionAdapter()
    event = adapter.normalize(
        raw_payload={"state": "on", "volume_percent": 65, "channel": "Sony SET"},
        household_id=HH_ID,
        device_id="dev_tv_001",
    )
    assert event.impact_level == ImpactLevel.LOW


# ─────────────────────────────────────────────────────────────
# Smart Fridge
# ─────────────────────────────────────────────────────────────

def test_smart_fridge_normal():
    adapter = SmartFridgeAdapter()
    event = adapter.normalize(
        raw_payload={"state": "closed", "door_open_seconds": 0, "temperature_c": 4.0},
        household_id=HH_ID,
        device_id="dev_fridge_001",
    )
    assert isinstance(event, NormalizedEvent)
    assert event.device_type == DeviceType.SMART_FRIDGE
    assert event.impact_level == ImpactLevel.INFO
    assert event.dedup_key is not None


def test_smart_fridge_door_open():
    adapter = SmartFridgeAdapter()
    event = adapter.normalize(
        raw_payload={"state": "door_open", "door_open_seconds": 200, "temperature_c": 6.0},
        household_id=HH_ID,
        device_id="dev_fridge_001",
    )
    assert event.impact_level == ImpactLevel.LOW


# ─────────────────────────────────────────────────────────────
# Adapter Registry
# ─────────────────────────────────────────────────────────────

def test_registry_returns_correct_adapter():
    assert isinstance(get_adapter(DeviceType.WATER_MOTOR), WaterMotorAdapter)
    assert isinstance(get_adapter(DeviceType.GEYSER), GeyserAdapter)
    assert isinstance(get_adapter(DeviceType.PRESSURE_COOKER), PressureCookerAdapter)
    assert isinstance(get_adapter(DeviceType.TELEVISION), TelevisionAdapter)
    assert isinstance(get_adapter(DeviceType.SMART_FRIDGE), SmartFridgeAdapter)


def test_registry_returns_none_for_unknown():
    assert get_adapter("unknown_device") is None


def test_registry_string_lookup():
    adapter = get_adapter("water_motor")
    assert isinstance(adapter, WaterMotorAdapter)


# ─────────────────────────────────────────────────────────────
# Event Ingestion + Dedup
# ─────────────────────────────────────────────────────────────

def test_ingest_returns_normalized_event():
    # Clear dedup cache before test
    _dedup_cache.clear()

    event = ingest(
        raw_payload={"state": "on", "tank_level_percent": 50, "flow_rate_lpm": 18.0},
        device_type="water_motor",
        household_id=HH_ID,
        device_id="dev_water_motor_001",
    )
    assert event is not None
    assert isinstance(event, NormalizedEvent)
    assert event.device_type == DeviceType.WATER_MOTOR


def test_ingest_duplicate_returns_none():
    """Calling ingest twice with same payload in same minute window returns None on 2nd call."""
    _dedup_cache.clear()

    payload = {"state": "on", "tank_level_percent": 50, "flow_rate_lpm": 18.0}

    first = ingest(
        raw_payload=payload,
        device_type="water_motor",
        household_id=HH_ID,
        device_id="dev_water_motor_002_dedup_test",
    )
    assert first is not None

    # Manually insert the same dedup_key with a future expiry to simulate same minute
    _dedup_cache[first.dedup_key] = 9999999999.0

    second = ingest(
        raw_payload=payload,
        device_type="water_motor",
        household_id=HH_ID,
        device_id="dev_water_motor_002_dedup_test",
    )
    assert second is None


def test_ingest_unknown_device_returns_none():
    event = ingest(
        raw_payload={"state": "on"},
        device_type="unknown_device_xyz",
        household_id=HH_ID,
        device_id="dev_unknown_001",
    )
    assert event is None


def test_ingest_life_event():
    event = ingest_life_event(
        event_type=EventType.GUEST_ARRIVAL,
        household_id=HH_ID,
        payload={"guest_count": 3, "relation": "extended_family"},
        affected_member_ids=["mbr_mama_004"],
        requires_ai=True,
    )
    assert isinstance(event, NormalizedEvent)
    assert event.event_type == EventType.GUEST_ARRIVAL
    assert event.requires_ai is True
    assert event.device_type is None
