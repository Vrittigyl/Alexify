"""
context_engine.py — Phase 9.2
==============================
Builds a HouseholdContext snapshot for each incoming event.
Used by both the RTE (complexity scoring) and Bedrock (full context).

Sources aggregated:
  - Graph version from graph_repository
  - Member presence from PresenceService
  - Device states from DynamoDB (2-min in-memory cache)
  - Active life events from HouseholdGraph LIFE_EVENT nodes
  - Last 10 RTE routing decisions from RTEAuditLog
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from config import settings
from db.dynamo_client import get_table, async_execute
from graph_repository import GraphRepository
from services.presence_service import PresenceService
from schemas.intelligence import HouseholdContext, MemberPresence

logger = logging.getLogger(__name__)

# IST = UTC+5:30 (fixed offset, no tzdata required)
_IST = timezone(timedelta(hours=5, minutes=30))
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class ContextEngine:
    """
    Builds HouseholdContext v2 from multiple live sources.
    Device state cache is refreshed every 2 minutes (stale_after_secs=120).
    """

    def __init__(
        self,
        graph_repo: GraphRepository | None = None,
        presence: PresenceService | None = None,
        device_state_stale_secs: int = 120,
    ):
        self._graph = graph_repo or GraphRepository()
        self._presence = presence or PresenceService()
        self._stale_secs = device_state_stale_secs

        # In-memory device state cache: household_id → (timestamp, {device_id: state_dict})
        self._device_cache: dict[str, tuple[float, dict[str, dict]]] = {}

    # ── Public API ───────────────────────────────────────────

    async def build(self, event, household_id: str) -> HouseholdContext:
        """
        Assembles a full HouseholdContext from all available sources.
        Fast path: each sub-call is cached; typical latency < 5ms.
        """
        now_ist = datetime.now(_IST)

        ctx = HouseholdContext(
            household_id=household_id,
            graph_cache_version=await async_execute(self._get_graph_version, household_id),
            members_presence=self._get_members_presence(household_id),
            device_states=await self._get_device_states(household_id),
            active_life_events=await async_execute(self._get_life_events, household_id),
            rte_routing_summary=await async_execute(self._get_rte_summary, household_id),
            time_of_day=self._time_of_day(now_ist),
            ist_time=now_ist.strftime("%H:%M"),
            day_of_week=_DAY_NAMES[now_ist.weekday()],
        )
        logger.debug(
            f"Context built: household={household_id} "
            f"members={len(ctx.members_presence)} "
            f"devices={len(ctx.device_states)} "
            f"life_events={len(ctx.active_life_events)}"
        )
        return ctx

    # ── Graph version ────────────────────────────────────────

    def _get_graph_version(self, household_id: str) -> int:
        try:
            return self._graph.get_graph_version(household_id)
        except Exception as e:
            logger.warning(f"Graph version fetch failed: {e}")
            return 0

    # ── Member presence ──────────────────────────────────────

    def _get_members_presence(self, household_id: str) -> list[MemberPresence]:
        records = self._presence.get_all(household_id)
        return [
            MemberPresence(
                member_id=r.member_id,
                room_id=r.room_id,
                is_home=r.is_home,
            )
            for r in records
        ]

    # ── Device states ────────────────────────────────────────

    async def _get_device_states(self, household_id: str) -> dict[str, dict]:
        cached = self._device_cache.get(household_id)
        if cached:
            ts, states = cached
            if (time.monotonic() - ts) < self._stale_secs:
                return states

        states = await async_execute(self._fetch_device_states_from_dynamo, household_id)
        self._device_cache[household_id] = (time.monotonic(), states)
        return states

    def _fetch_device_states_from_dynamo(self, household_id: str) -> dict[str, dict]:
        """Scan HouseholdGraph for node_type=device and return their state."""
        try:
            table = get_table("household_graph")
            from boto3.dynamodb.conditions import Key, Attr
            resp = table.query(
                KeyConditionExpression=Key("household_id").eq(household_id),
                FilterExpression=Attr("node_type").eq("device"),
            )
            states = {}
            for item in resp.get("Items", []):
                dev_id = item.get("node_id")
                if dev_id:
                    states[dev_id] = {
                        "device_type": item.get("device_type"),
                        "state":       item.get("state"),
                        "room_id":     item.get("room_id"),
                    }
            return states
        except Exception as e:
            logger.warning(f"Device state fetch failed: {e}")
            return {}

    # ── Life events ──────────────────────────────────────────

    def _get_life_events(self, household_id: str) -> list[dict]:
        """Pull active LIFE_EVENT nodes from HouseholdGraph."""
        try:
            table = get_table("household_graph")
            from boto3.dynamodb.conditions import Key, Attr
            resp = table.query(
                KeyConditionExpression=Key("household_id").eq(household_id),
                FilterExpression=Attr("node_type").eq("life_event"),
            )
            return [
                {
                    "event_id":        item.get("node_id"),
                    "event_type":      item.get("event_type"),
                    "member_id":       item.get("member_id"),
                    "remaining_days":  item.get("remaining_days"),
                    "constraints":     item.get("constraints", []),
                }
                for item in resp.get("Items", [])
            ]
        except Exception as e:
            logger.warning(f"Life events fetch failed: {e}")
            return []

    # ── RTE routing summary ──────────────────────────────────

    def _get_rte_summary(self, household_id: str) -> list[dict]:
        """Last 10 RTEAuditLog decisions for this household."""
        try:
            table = get_table("rte_audit_log")
            from boto3.dynamodb.conditions import Key
            resp = table.query(
                IndexName="household_id-timestamp-index",
                KeyConditionExpression=Key("household_id").eq(household_id),
                ScanIndexForward=False,
                Limit=10,
            )
            return [
                {
                    "event_id":    item.get("event_id"),
                    "route":       item.get("route"),
                    "stage":       item.get("stage_decided"),
                    "timestamp":   item.get("timestamp"),
                }
                for item in resp.get("Items", [])
            ]
        except Exception as e:
            # RTEAuditLog may not have GSI in local DynamoDB — soft fail
            logger.debug(f"RTE summary unavailable: {e}")
            return []

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _time_of_day(dt: datetime) -> str:
        h = dt.hour
        if 5 <= h < 9:   return "early_morning"
        if 9 <= h < 12:  return "morning"
        if 12 <= h < 14: return "midday"
        if 14 <= h < 17: return "afternoon"
        if 17 <= h < 20: return "evening"
        if 20 <= h < 23: return "night"
        return "late_night"
