"""
event_simulator.py — Phase 10.5
=================================
EventSimulator: loads demo_script.json and fires each event through the
full SAATHI pipeline with realistic timing (asyncio.sleep between events).

Also provides named convenience methods used by the REST API:
  simulate_water_tank_full()
  simulate_board_exam()
  simulate_guest_arrival()
  ... etc.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Callable

from schemas import NormalizedEvent
from schemas.enums import DeviceType, EventType, ImpactLevel

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"

_ET_MAP = {
    "schedule_event":       EventType.SCHEDULE_EVENT,
    "life_event":           EventType.LIFE_EVENT,
    "guest_arrival":        EventType.GUEST_ARRIVAL,
    "routine_trigger":      EventType.ROUTINE_TRIGGER,
    "health_alert":         EventType.HEALTH_ALERT,
    "festival_declaration": EventType.FESTIVAL_DECLARATION,
    "health_emergency":     EventType.HEALTH_EMERGENCY,
    "presence_update":      EventType.PRESENCE_UPDATE,
}

_DT_MAP = {
    "water_motor":     DeviceType.WATER_MOTOR,
    "geyser":          DeviceType.GEYSER,
    "pressure_cooker": DeviceType.PRESSURE_COOKER,
    "television":      DeviceType.TELEVISION,
    "smart_fridge":    DeviceType.SMART_FRIDGE,
    "ac":              DeviceType.AC,
    "light":           DeviceType.LIGHT,
}


class EventSimulator:
    """
    Async event playback engine.
    `pipeline_fn` is the async callable that receives NormalizedEvent and returns actions.
    """

    def __init__(
        self,
        household_id: str,
        pipeline_fn: Callable,
        speed_multiplier: float = 10.0,
    ):
        self._hh = household_id
        self._pipeline = pipeline_fn
        self._speed = speed_multiplier  # 10x faster than real-time by default
        self._running = False

    # ── Named event builders ──────────────────────────────────

    def water_tank_full(self) -> NormalizedEvent:
        return NormalizedEvent(
            household_id=self._hh,
            event_type=EventType.DEVICE_STATE,
            device_type=DeviceType.WATER_MOTOR,
            device_id="dev_water_motor_001",
            payload={"tank_level_percent": 96, "state": "on", "flow_rate_lpm": 5.1},
            impact_level=ImpactLevel.HIGH,
        )

    def board_exam(self) -> NormalizedEvent:
        return NormalizedEvent(
            household_id=self._hh,
            event_type=EventType.LIFE_EVENT,
            payload={
                "event": "board_exams",
                "member_id": "mbr_rohan_005",
                "remaining_days": 6,
                "constraints": ["quiet_hours", "reduce_distractions"],
            },
            impact_level=ImpactLevel.HIGH,
        )

    def guest_arrival(self) -> NormalizedEvent:
        return NormalizedEvent(
            household_id=self._hh,
            event_type=EventType.GUEST_ARRIVAL,
            payload={"guest_count": 3, "relation": "extended_family"},
            impact_level=ImpactLevel.MEDIUM,
        )

    def pressure_cooker_5_whistles(self) -> NormalizedEvent:
        return NormalizedEvent(
            household_id=self._hh,
            event_type=EventType.DEVICE_STATE,
            device_type=DeviceType.PRESSURE_COOKER,
            device_id="dev_pressure_cooker_001",
            payload={"whistle_count": 5, "state": "on", "temperature_c": 121},
            impact_level=ImpactLevel.HIGH,
        )

    def dadaji_medicine(self) -> NormalizedEvent:
        return NormalizedEvent(
            household_id=self._hh,
            event_type=EventType.ROUTINE_TRIGGER,
            payload={"routine_id": "rtn_dadaji_evening_meds", "member_id": "mbr_dadaji_001"},
        )

    def fridge_door_open(self) -> NormalizedEvent:
        from services.bedrock_layer import _find_device_id
        fridge_id = _find_device_id(self._hh, "smart_fridge", "Kitchen", "dev_fridge_001")
        if not fridge_id:
            fridge_id = _find_device_id(self._hh, "smart_fridge", None, "dev_fridge_001")
        return NormalizedEvent(
            household_id=self._hh,
            event_type=EventType.DEVICE_STATE,
            device_type=DeviceType.SMART_FRIDGE,
            device_id=fridge_id,
            payload={"state": "door_open", "door_open_seconds": 210, "temperature_c": 8.2},
        )

    # ── Full demo playback ────────────────────────────────────

    async def run_demo(self) -> list[dict]:
        """
        Load demo_script.json and play back every event through the pipeline.
        Returns list of result dicts with event_name, route, actions_count, latency.
        """
        try:
            with open(_DATA_DIR / "demo_script.json", encoding="utf-8") as f:
                demo_events = json.load(f)
        except FileNotFoundError:
            logger.error("demo_script.json not found")
            return []

        results = []
        self._running = True
        prev_t = 0

        for entry in demo_events:
            if not self._running:
                break

            t_offset = entry.get("t_seconds", 0)
            wait = (t_offset - prev_t) / self._speed
            if wait > 0:
                await asyncio.sleep(wait)
            prev_t = t_offset

            event = self._build_event(entry)
            if not event:
                continue

            start = time.monotonic()
            try:
                result = await self._pipeline(event)
                latency_ms = (time.monotonic() - start) * 1000
                results.append({
                    "event_name": entry.get("event_name"),
                    "event_id": event.event_id,
                    "route": result.get("route", "UNKNOWN"),
                    "actions_count": result.get("actions_count", 0),
                    "latency_ms": round(latency_ms, 1),
                })
                logger.info(
                    f"Simulator: {entry['event_name']} -> "
                    f"route={result.get('route')} "
                    f"actions={result.get('actions_count', 0)} "
                    f"latency={latency_ms:.1f}ms"
                )
            except Exception as e:
                logger.error(f"Simulator: pipeline error for {entry['event_name']}: {e}")

        self._running = False
        return results

    def stop(self) -> None:
        self._running = False

    # ── Builder ──────────────────────────────────────────────

    def _build_event(self, entry: dict) -> NormalizedEvent | None:
        try:
            raw = entry.get("raw_payload", {})
            if entry.get("device_type"):
                event_type = EventType.DEVICE_STATE
            else:
                et_str = raw.get("event_type", "life_event")
                event_type = _ET_MAP.get(et_str, EventType.LIFE_EVENT)

            device_type = _DT_MAP.get(entry.get("device_type") or "", None)
            payload = {k: v for k, v in raw.items() if k != "event_type"}

            return NormalizedEvent(
                household_id=self._hh,
                event_type=event_type,
                device_type=device_type,
                device_id=entry.get("device_id"),
                payload=payload,
            )
        except Exception as e:
            logger.warning(f"Simulator: could not build event from {entry}: {e}")
            return None
