"""
services/bootstrap_engine.py — Phase 12B
==========================================
Household Learning Bootstrap Engine.

PURPOSE
-------
When a new household is onboarded, their dashboard is blank.
This engine populates it with real AI-generated intelligence by:

  1. Reading the household's graph from DynamoDB (members, devices, routines).
     Zero hardcoded data — everything comes from /graph/{hh}/full.

  2. Generating realistic historical NormalizedEvents derived exclusively
     from the nodes and edges that onboarding wrote.

  3. Feeding those events through the full SAATHI pipeline
     (ContextEngine → RTE → RuleEngine/Bedrock → PatternEngine).

  4. Writing accumulated PatternRecords that reflect weeks of observation,
     then running pattern promotion so rules appear on the dashboard.

GUARANTEE
---------
No Sharma references.
No hardcoded family names.
No assumed member IDs.
Every event ID, device ID, and member ID comes from DynamoDB.

API
---
  POST /bootstrap/{household_id}          — run bootstrap for a household
  GET  /bootstrap/{household_id}/status   — progress + result summary
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

import networkx as nx

from graph_repository import GraphRepository, _decimal_to_native
from schemas.enums import (
    ConfidenceBand,
    DeviceType,
    EventType,
    ImpactLevel,
)
from schemas.intelligence import PatternRecord
from schemas import NormalizedEvent
from db.dynamo_client import get_table

logger = logging.getLogger(__name__)

# ── Device type → EventType mapping ───────────────────────────────────────────
# What kind of event does each device type naturally generate?
_DEVICE_EVENT_TYPE = {
    "ac":              EventType.DEVICE_STATE,
    "television":      EventType.DEVICE_STATE,
    "water_motor":     EventType.DEVICE_STATE,
    "geyser":          EventType.DEVICE_STATE,
    "smart_fridge":    EventType.DEVICE_STATE,
    "pressure_cooker": EventType.DEVICE_STATE,
    "light":           EventType.DEVICE_STATE,
    "other":           EventType.DEVICE_STATE,
}

# Device type → a realistic set of payloads that would trigger rules
_DEVICE_PAYLOADS: dict[str, list[dict]] = {
    "water_motor": [
        {"state": "on", "tank_level_percent": 30, "flow_rate_lpm": 5.1},
        {"state": "on", "tank_level_percent": 60, "flow_rate_lpm": 4.8},
        {"state": "on", "tank_level_percent": 96, "flow_rate_lpm": 2.1},  # triggers tank_full rule
        {"state": "off", "tank_level_percent": 97, "flow_rate_lpm": 0},
    ],
    "geyser": [
        {"state": "on", "temperature_c": 42, "running_minutes": 10},
        {"state": "on", "temperature_c": 55, "running_minutes": 25},
        {"state": "on", "temperature_c": 60, "running_minutes": 31},   # triggers auto-off rule
        {"state": "off", "temperature_c": 40, "running_minutes": 0},
    ],
    "pressure_cooker": [
        {"state": "on", "whistle_count": 2, "temperature_c": 110},
        {"state": "on", "whistle_count": 4, "temperature_c": 118},
        {"state": "on", "whistle_count": 5, "temperature_c": 121},     # triggers whistle rule
    ],
    "television": [
        {"state": "on", "volume_percent": 35, "channel": "news"},
        {"state": "on", "volume_percent": 50, "channel": "entertainment"},
        {"state": "on", "volume_percent": 65, "channel": "entertainment"},  # triggers quiet hours
        {"state": "off", "volume_percent": 0},
    ],
    "smart_fridge": [
        {"state": "door_closed", "temperature_c": 4, "door_open_seconds": 0},
        {"state": "door_open", "temperature_c": 6, "door_open_seconds": 45},
        {"state": "door_open", "temperature_c": 8, "door_open_seconds": 210},  # triggers fridge rule
    ],
    "ac": [
        {"state": "on", "temperature_set_c": 24, "mode": "cool"},
        {"state": "on", "temperature_set_c": 26, "mode": "fan"},
        {"state": "off", "temperature_set_c": 26},
    ],
    "light": [
        {"state": "on", "brightness_pct": 80},
        {"state": "off", "brightness_pct": 0},
    ],
    "other": [
        {"state": "on"},
        {"state": "off"},
    ],
}

# DeviceType string → SAATHI DeviceType enum
_DT_ENUM: dict[str, DeviceType | None] = {
    "ac":              DeviceType.AC,
    "television":      DeviceType.TELEVISION,
    "water_motor":     DeviceType.WATER_MOTOR,
    "geyser":          DeviceType.GEYSER,
    "smart_fridge":    DeviceType.SMART_FRIDGE,
    "pressure_cooker": DeviceType.PRESSURE_COOKER,
    "light":           DeviceType.LIGHT,
    "other":           None,
}

# Routine ID → how to translate it into an EventType
_ROUTINE_TO_EVENT_TYPE: dict[str, EventType] = {
    "medicine_morning": EventType.ROUTINE_TRIGGER,
    "medicine_night":   EventType.ROUTINE_TRIGGER,
    "morning_tea":      EventType.ROUTINE_TRIGGER,
    "prayer_time":      EventType.ROUTINE_TRIGGER,
    "evening_walk":     EventType.ROUTINE_TRIGGER,
    "dinner_together":  EventType.ROUTINE_TRIGGER,
    "school_run":       EventType.ROUTINE_TRIGGER,
    "work_from_home":   EventType.SCHEDULE_EVENT,
    "movie_night":      EventType.ROUTINE_TRIGGER,
    "afternoon_nap":    EventType.ROUTINE_TRIGGER,
}


# ─────────────────────────────────────────────────────────────────────────────
# Graph reader
# ─────────────────────────────────────────────────────────────────────────────

class HouseholdGraphReader:
    """
    Reads the household graph from DynamoDB.
    Returns structured dicts of members, devices, routines — all from real data.
    """

    def __init__(self, household_id: str):
        self.household_id = household_id
        self._repo = GraphRepository()

    def read(self) -> dict[str, Any]:
        """
        Returns a dict with:
          family_name, location, members[], devices[], routines[], edges[]
        Every value comes from DynamoDB — nothing invented.
        """
        try:
            g: nx.DiGraph = self._repo.load_graph(self.household_id, force_reload=True)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot load graph for {self.household_id}: {exc}. "
                "Has this household been onboarded?"
            ) from exc

        family_name = g.graph.get("family_name", "Unknown Family")
        location    = g.graph.get("location", "Unknown City")

        members:  list[dict] = []
        devices:  list[dict] = []
        routines: list[dict] = []

        for node_id, attrs in g.nodes(data=True):
            ntype = attrs.get("node_type")
            if ntype == "member":
                members.append({
                    "node_id":   node_id,
                    "name":      attrs.get("name", node_id),
                    "role":      attrs.get("role", "adult"),
                    "age_group": attrs.get("age_group", "adult"),
                    "age":       attrs.get("age", 30),
                    "care_needs": attrs.get("care_needs", []),
                    "notification_channel": attrs.get("notification_channel", "mobile_push"),
                })
            elif ntype == "device":
                devices.append({
                    "node_id":     node_id,
                    "name":        attrs.get("name", node_id),
                    "device_type": attrs.get("device_type", "other"),
                    "room":        attrs.get("room", "home"),
                })
            elif ntype == "routine":
                routines.append({
                    "node_id":     node_id,
                    "description": attrs.get("description", node_id),
                    "time_window": attrs.get("time_window"),
                    "days":        attrs.get("days", []),
                })

        # Collect edges for relationship context
        edges: list[dict] = []
        for u, v, edata in g.edges(data=True):
            edges.append({
                "from":  u,
                "type":  edata.get("edge_type", ""),
                "to":    v,
            })

        logger.info(
            f"HouseholdGraphReader: {self.household_id} → "
            f"{len(members)} members, {len(devices)} devices, {len(routines)} routines"
        )

        if not members:
            raise RuntimeError(
                f"No member nodes found for {self.household_id}. "
                "Check that /onboarding/complete was called successfully."
            )

        return {
            "household_id": self.household_id,
            "family_name":  family_name,
            "location":     location,
            "members":      members,
            "devices":      devices,
            "routines":     routines,
            "edges":        edges,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Event generator
# ─────────────────────────────────────────────────────────────────────────────

class HouseholdEventGenerator:
    """
    Given the household graph data, generates a stream of NormalizedEvents.
    All device IDs, member IDs, and event types come from the graph.
    No fallback to Sharma data. No hardcoded names.
    """

    def __init__(self, graph_data: dict[str, Any]):
        self._hh_id    = graph_data["household_id"]
        self._members  = graph_data["members"]
        self._devices  = graph_data["devices"]
        self._routines = graph_data["routines"]
        self._edges    = graph_data["edges"]

        # Build quick lookup: member_id → member, device_id → device
        self._member_by_id = {m["node_id"]: m for m in self._members}
        self._device_by_id = {d["node_id"]: d for d in self._devices}

        # Which device does each member primarily use?
        self._primary_device: dict[str, str] = {}  # member_id → device_id
        for e in self._edges:
            if e["type"] == "PRIMARY_USER_OF":
                self._primary_device[e["from"]] = e["to"]

        # Which routines does each member follow?
        self._member_routines: dict[str, list[dict]] = {}
        rtn_by_id = {r["node_id"]: r for r in self._routines}
        for e in self._edges:
            if e["type"] == "FOLLOWS":
                mbr_id = e["from"]
                rtn_id = e["to"]
                rtn    = rtn_by_id.get(rtn_id)
                if rtn:
                    self._member_routines.setdefault(mbr_id, []).append(rtn)

    def generate_daily_events(
        self,
        date_offset_days: int = 0,
        num_events: int = 6,
    ) -> list[NormalizedEvent]:
        """
        Generate a realistic day's worth of events.
        date_offset_days = 0 → today; -1 → yesterday; -30 → 30 days ago.
        """
        events: list[NormalizedEvent] = []
        rng = random.Random(date_offset_days)  # deterministic per day

        # ── Device events — based on real device list ────────────────────
        devices_to_fire = rng.sample(
            self._devices, min(len(self._devices), max(2, num_events // 2))
        )
        for dev in devices_to_fire:
            event = self._make_device_event(dev, rng)
            if event:
                events.append(event)

        # ── Routine trigger events — based on real routine list ──────────
        routines_today = [r for r in self._routines if r.get("days") or True]
        if routines_today:
            for rtn in rng.sample(routines_today, min(len(routines_today), num_events // 2 + 1)):
                event = self._make_routine_event(rtn, rng)
                if event:
                    events.append(event)

        return events

    def _make_device_event(self, dev: dict, rng: random.Random) -> NormalizedEvent | None:
        """Create a device state event from a real device node."""
        dev_type_str = dev.get("device_type", "other")
        payloads     = _DEVICE_PAYLOADS.get(dev_type_str, _DEVICE_PAYLOADS["other"])
        payload      = rng.choice(payloads)
        device_enum  = _DT_ENUM.get(dev_type_str)
        event_type   = _DEVICE_EVENT_TYPE.get(dev_type_str, EventType.DEVICE_STATE)

        # Find a member who uses this device for context
        primary_user = next(
            (mbr_id for mbr_id, dev_id in self._primary_device.items() if dev_id == dev["node_id"]),
            None,
        )
        affected_members = [primary_user] if primary_user else []

        return NormalizedEvent(
            household_id=self._hh_id,
            event_type=event_type,
            device_type=device_enum,
            device_id=dev["node_id"],
            payload=payload,
            impact_level=ImpactLevel.MEDIUM,
            affected_member_ids=affected_members,
        )

    def _make_routine_event(self, rtn: dict, rng: random.Random) -> NormalizedEvent | None:
        """Create a routine trigger event from a real routine node."""
        node_id = rtn["node_id"]
        # Extract the routine base name from node_id (e.g. rtn_medicine_morning_001 → medicine_morning)
        # Strip "rtn_" prefix and "_NNN" suffix
        parts = node_id.replace("rtn_", "")
        # Remove trailing _NNN sequence counter
        import re
        routine_base = re.sub(r"_\d+$", "", parts)

        event_type = _ROUTINE_TO_EVENT_TYPE.get(routine_base, EventType.ROUTINE_TRIGGER)

        # Find a member who follows this routine
        follower = next(
            (mbr_id for mbr_id, rtns in self._member_routines.items()
             if any(r["node_id"] == node_id for r in rtns)),
            self._members[0]["node_id"] if self._members else None,
        )

        payload: dict = {"routine_id": node_id}
        if follower:
            payload["member_id"] = follower

        # Add time if available
        tw = rtn.get("time_window")
        if tw:
            start = tw.split("-")[0] if tw else None
            if start:
                payload["scheduled_time"] = start

        return NormalizedEvent(
            household_id=self._hh_id,
            event_type=event_type,
            payload=payload,
            impact_level=ImpactLevel.LOW,
            affected_member_ids=[follower] if follower else [],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pattern seeder
# ─────────────────────────────────────────────────────────────────────────────

class PatternSeeder:
    """
    Writes accumulated PatternRecord entries directly to DynamoDB.

    This simulates weeks of pattern observation without having to replay
    weeks of events in real time. The PatternRecord values are derived
    purely from the household graph (device types, member roles, routines).

    IMPORTANT: We never invent patterns that aren't rooted in what's in the graph.
    Each pattern maps to an actual (member_id, device_id) or (routine_id) pair
    that was created during onboarding.
    """

    def __init__(self, household_id: str, graph_data: dict[str, Any]):
        self._hh     = household_id
        self._graph  = graph_data
        self._table  = get_table("household_patterns")

    def seed(self, days_of_history: int = 35) -> list[str]:
        """
        Create PatternRecord entries for the household.
        Returns list of pattern_ids written.
        """
        now      = datetime.now(tz=timezone.utc)
        members  = self._graph["members"]
        devices  = self._graph["devices"]
        routines = self._graph["routines"]
        edges    = self._graph["edges"]

        # Build member → devices mapping from PRIMARY_USER_OF edges
        member_devices: dict[str, list[dict]] = {}
        dev_by_id = {d["node_id"]: d for d in devices}
        for e in edges:
            if e["type"] == "PRIMARY_USER_OF":
                member_devices.setdefault(e["from"], []).append(dev_by_id[e["to"]])

        # Build member → routines mapping
        rtn_by_id = {r["node_id"]: r for r in routines}
        member_routines: dict[str, list[dict]] = {}
        for e in edges:
            if e["type"] == "FOLLOWS":
                rtn = rtn_by_id.get(e["to"])
                if rtn:
                    member_routines.setdefault(e["from"], []).append(rtn)

        written: list[str] = []
        items_to_write: list[dict] = []

        # ── Per-member per-device patterns ────────────────────────────────
        for member in members:
            mbr_id   = member["node_id"]
            mbr_role = member.get("role", "adult")
            devs     = member_devices.get(mbr_id, [])

            for dev in devs:
                dev_id      = dev["node_id"]
                dev_type    = dev.get("device_type", "other")
                dev_type_sk = dev_type

                # Confidence is higher for seniors (more consistent routines)
                base_confidence = 0.92 if mbr_role in ("grandparent", "senior") else 0.75
                # Add randomness per pattern (±10%)
                rng = random.Random(f"{mbr_id}_{dev_id}")
                confidence = round(min(0.98, max(0.40, base_confidence + rng.uniform(-0.10, 0.10))), 3)

                # Derive time_window from routines the member follows
                time_window = self._infer_time_window(mbr_id, dev_type, member_routines, rtn_by_id)

                pattern_id = f"ptn_{mbr_id}_{dev_type_sk}"
                obs_days   = days_of_history + rng.randint(-5, 5)
                total_obs  = obs_days
                # Matches ≈ confidence * observations, floored
                total_matches = max(1, int(confidence * total_obs))

                first_observed = now - timedelta(days=obs_days)
                last_observed  = now - timedelta(hours=rng.randint(2, 36))

                # Determine band based on confidence + days
                band = PatternRecord.compute_band(confidence, obs_days)

                record = self._build_record(
                    pattern_id   = pattern_id,
                    member_id    = mbr_id,
                    dev_type_str = dev_type,
                    dev_id       = dev_id,
                    confidence   = confidence,
                    band         = band,
                    obs_days     = obs_days,
                    total_obs    = total_obs,
                    total_matches= total_matches,
                    first_obs    = first_observed,
                    last_obs     = last_observed,
                    time_window  = time_window,
                    now          = now,
                    description  = f"{member['name']} uses {dev.get('name', dev_type)} regularly",
                    day_pattern  = self._day_pattern_for_role(mbr_role, rng),
                )
                items_to_write.append(record)
                written.append(pattern_id)

            # ── Routine-based patterns ─────────────────────────────────────
            for rtn in member_routines.get(mbr_id, []):
                rtn_id  = rtn["node_id"]
                import re
                rtn_base = re.sub(r"_\d+$", "", rtn_id.replace("rtn_", ""))
                pat_id  = f"ptn_{mbr_id}_{rtn_base}"

                rng2 = random.Random(f"{mbr_id}_{rtn_id}")
                is_medication = "medicine" in rtn_base
                conf = round(
                    min(0.97, max(0.45,
                        (0.93 if is_medication else 0.72) + rng2.uniform(-0.08, 0.08)
                    )),
                    3,
                )
                obs_days2     = days_of_history + rng2.randint(-3, 3)
                total_obs2    = obs_days2
                total_matches2 = max(1, int(conf * total_obs2))
                band2         = PatternRecord.compute_band(conf, obs_days2)

                time_window2 = rtn.get("time_window")
                if time_window2 and "-" in time_window2:
                    # normalise: "08:30-08:30" → "08:30-09:00"
                    parts2 = time_window2.split("-")
                    if parts2[0] == parts2[1]:
                        time_window2 = f"{parts2[0]}-{parts2[0]}"  # keep same

                record2 = self._build_record(
                    pattern_id   = pat_id,
                    member_id    = mbr_id,
                    dev_type_str = None,
                    dev_id       = None,
                    confidence   = conf,
                    band         = band2,
                    obs_days     = obs_days2,
                    total_obs    = total_obs2,
                    total_matches= total_matches2,
                    first_obs    = now - timedelta(days=obs_days2),
                    last_obs     = now - timedelta(hours=rng2.randint(1, 24)),
                    time_window  = time_window2,
                    now          = now,
                    description  = rtn.get("description", rtn_base.replace("_", " ")),
                    day_pattern  = rtn.get("days") or ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    event_type   = EventType.ROUTINE_TRIGGER,
                )
                items_to_write.append(record2)
                written.append(pat_id)

        # Batch write to DynamoDB
        self._batch_write(items_to_write)
        logger.info(f"PatternSeeder: wrote {len(written)} patterns for {self._hh}")
        return written

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _infer_time_window(
        self,
        member_id: str,
        device_type: str,
        member_routines: dict[str, list[dict]],
        rtn_by_id: dict[str, dict],
    ) -> str | None:
        """
        Infer a plausible time_window for a device usage pattern
        based on the member's routines.
        """
        # Morning devices: geyser → morning window
        if device_type == "geyser":
            return "06:30-07:15"
        if device_type == "water_motor":
            return "08:30-08:45"
        # TV typically evening
        if device_type == "television":
            return "21:00-22:30"
        # AC — check if member has a routine around 6 PM
        if device_type == "ac":
            rtns = member_routines.get(member_id, [])
            for r in rtns:
                tw = r.get("time_window")
                if tw and tw.startswith(("17:", "18:", "19:")):
                    return tw
            return "18:00-22:00"
        # For other devices use routines as a hint
        rtns = member_routines.get(member_id, [])
        if rtns:
            tw = rtns[0].get("time_window")
            if tw:
                return tw
        return None

    def _day_pattern_for_role(self, role: str, rng: random.Random) -> list[str]:
        """Return a realistic day pattern given the member's role."""
        all_days  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekdays  = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        if role in ("grandparent", "senior"):
            return all_days  # elderly tend to be home every day
        if role in ("child",):
            return weekdays   # school-going kids on weekdays
        # Default: mostly every day, skip one random day
        skip = rng.choice(all_days)
        return [d for d in all_days if d != skip]

    def _build_record(
        self,
        pattern_id: str,
        member_id: str | None,
        dev_type_str: str | None,
        dev_id: str | None,
        confidence: float,
        band: ConfidenceBand,
        obs_days: int,
        total_obs: int,
        total_matches: int,
        first_obs: datetime,
        last_obs: datetime,
        time_window: str | None,
        now: datetime,
        description: str,
        day_pattern: list[str],
        event_type: EventType | None = None,
    ) -> dict:
        dev_type_enum_val = None
        if dev_type_str:
            dt = _DT_ENUM.get(dev_type_str)
            if dt:
                dev_type_enum_val = dt.value

        item: dict[str, Any] = {
            "household_id":       self._hh,
            "pattern_id":         pattern_id,
            "description":        description,
            "confidence":         Decimal(str(confidence)),
            "confidence_band":    band.value,
            "observation_days":   obs_days,
            "total_observations": total_obs,
            "total_matches":      total_matches,
            "consecutive_misses": 0,
            "consecutive_overrides": 0,
            "first_observed":     first_obs.isoformat(),
            "last_observed":      last_obs.isoformat(),
            "created_at":         now.isoformat(),
        }
        if member_id:
            item["member_id"] = member_id
        if dev_type_enum_val:
            item["device_type"] = dev_type_enum_val
        if dev_id:
            item["device_id"] = dev_id
        if time_window:
            item["time_window"] = time_window
        if day_pattern:
            item["day_pattern"] = day_pattern
        if event_type:
            item["event_type"] = event_type.value

        # promoted_at for PROMOTED band
        if band == ConfidenceBand.PROMOTED:
            promoted_days_ago = max(1, obs_days - 30)
            item["promoted_at"] = (now - timedelta(days=promoted_days_ago)).isoformat()

        return item

    def _batch_write(self, items: list[dict]) -> None:
        """Write items to HouseholdPatterns in DynamoDB batches of 25."""
        CHUNK = 25
        for i in range(0, len(items), CHUNK):
            chunk = items[i : i + CHUNK]
            with self._table.batch_writer() as bw:
                for item in chunk:
                    bw.put_item(Item=item)


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class BootstrapEngine:
    """
    Orchestrates the full bootstrap sequence for a cold-start household.

    Steps:
      1. Read graph from DynamoDB (no mock fallback)
      2. Seed PatternRecords (simulate weeks of learning)
      3. Replay recent events through the live pipeline (populates ActionLog + RTEAuditLog)
      4. Promote eligible patterns to rules
    """

    def __init__(self, pipeline_fn: Callable):
        """
        pipeline_fn — the async callable run_full_pipeline(event) from main.py.
        Injected so bootstrap uses the SAME pipeline as production.
        """
        self._pipeline = pipeline_fn
        self._running_jobs: dict[str, dict] = {}

    async def run(
        self,
        household_id: str,
        days_of_history: int = 35,
        live_event_days: int = 3,
        events_per_day: int = 5,
    ) -> dict[str, Any]:
        """
        Full bootstrap sequence. Returns a summary dict.

        Args:
          household_id     — target household (must be onboarded)
          days_of_history  — how many observation days to simulate for patterns
          live_event_days  — how many days of live events to replay through pipeline
          events_per_day   — events to generate per live day
        """
        start_ts = time.monotonic()
        job_id   = uuid.uuid4().hex[:8]
        self._running_jobs[household_id] = {"status": "running", "job_id": job_id}

        logger.info(f"Bootstrap[{job_id}]: starting for household={household_id}")

        # ── Step 1: Read graph ──────────────────────────────────────────────
        reader     = HouseholdGraphReader(household_id)
        graph_data = reader.read()

        family_name  = graph_data["family_name"]
        member_count = len(graph_data["members"])
        device_count = len(graph_data["devices"])
        routine_count = len(graph_data["routines"])

        logger.info(
            f"Bootstrap[{job_id}]: {family_name} — "
            f"{member_count} members, {device_count} devices, {routine_count} routines"
        )

        # ── Step 2: Seed patterns ───────────────────────────────────────────
        seeder      = PatternSeeder(household_id, graph_data)
        pattern_ids = seeder.seed(days_of_history=days_of_history)

        logger.info(f"Bootstrap[{job_id}]: seeded {len(pattern_ids)} patterns")

        # ── Step 3: Replay recent live events through pipeline ──────────────
        generator  = HouseholdEventGenerator(graph_data)
        pipeline_results: list[dict] = []

        for day_offset in range(-live_event_days, 0):   # last N days
            events = generator.generate_daily_events(
                date_offset_days=day_offset,
                num_events=events_per_day,
            )
            for event in events:
                try:
                    result = await self._pipeline(event)
                    pipeline_results.append({
                        "event_id":    event.event_id,
                        "route":       result.get("route", "UNKNOWN"),
                        "actions":     result.get("actions_count", 0),
                        "latency_ms":  result.get("total_latency_ms", 0),
                    })
                except Exception as exc:
                    logger.warning(f"Bootstrap[{job_id}]: pipeline error: {exc}")
                # Small yield so we don't block the event loop
                await asyncio.sleep(0.05)

        logger.info(
            f"Bootstrap[{job_id}]: replayed {len(pipeline_results)} events through pipeline"
        )

        # ── Step 4: Promote eligible patterns ──────────────────────────────
        from services.pattern_engine import PatternEngine
        pe              = PatternEngine()
        newly_promoted  = pe.promote_if_eligible(household_id)

        logger.info(
            f"Bootstrap[{job_id}]: promoted {len(newly_promoted)} patterns to rules"
        )

        elapsed = round((time.monotonic() - start_ts) * 1000, 1)
        summary = {
            "household_id":       household_id,
            "family_name":        family_name,
            "job_id":             job_id,
            "status":             "complete",
            "members":            member_count,
            "devices":            device_count,
            "routines":           routine_count,
            "patterns_seeded":    len(pattern_ids),
            "events_replayed":    len(pipeline_results),
            "patterns_promoted":  len(newly_promoted),
            "promoted_rule_ids":  newly_promoted,
            "elapsed_ms":         elapsed,
        }
        self._running_jobs[household_id] = {"status": "complete", **summary}
        logger.info(f"Bootstrap[{job_id}]: complete in {elapsed}ms")
        return summary

    def get_status(self, household_id: str) -> dict | None:
        return self._running_jobs.get(household_id)
