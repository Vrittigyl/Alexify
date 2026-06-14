"""
services/onboarding_service.py
================================
Translates an OnboardingPayload into graph nodes + edges,
then writes them to DynamoDB (HouseholdGraph table).

Design rules:
  - No Sharma references
  - No hardcoded data
  - Pure function: payload → nodes + edges
  - Idempotent: can be called multiple times for the same household_id
    (put_item is idempotent on PK/SK collision)

Node ID conventions
-------------------
  members   : mbr_<slug>_<seq>  e.g. mbr_imran_001
  devices   : dev_<type>_<seq>  e.g. dev_ac_001
  routines  : rtn_<id>_<seq>    e.g. rtn_medicine_morning_001
  care needs: (encoded as edges member → care_type, no separate node)
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from db.dynamo_client import get_table

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────

def _slug(text: str) -> str:
    """Convert arbitrary string to lowercase slug safe for IDs."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:20]


def _floats_to_decimal(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimal(i) for i in obj]
    return obj


# Age group → approximate midpoint age for graph display
_AGE_GROUP_MIDPOINT = {
    "baby": 1,
    "child": 8,
    "teen": 15,
    "adult": 35,
    "senior": 68,
}

# Role → notification channel default
_ROLE_CHANNEL = {
    "grandparent": "alexa_voice",
    "parent": "mobile_push",
    "owner": "mobile_push",
    "partner": "mobile_push",
    "child": "alexa_voice",
    "teen": "mobile_push",
    "other": "mobile_push",
}

# Device type → internal SAATHI device_type enum value
_DEVICE_TYPE_MAP = {
    "ac": "ac",
    "tv": "television",
    "water_motor": "water_motor",
    "geyser": "geyser",
    "fridge": "smart_fridge",
    "washing_machine": "other",
    "pressure_cooker": "pressure_cooker",
    "lights": "light",
    "security_camera": "other",
    "doorbell": "other",
    "other": "other",
}

# Routine id → graph description
_ROUTINE_DESCRIPTIONS = {
    "morning_tea": "Morning tea / chai",
    "school_run": "School drop-off",
    "medicine_morning": "Morning medication round",
    "work_from_home": "Work from home",
    "afternoon_nap": "Afternoon nap",
    "evening_walk": "Evening walk",
    "dinner_together": "Family dinner together",
    "medicine_night": "Night medication round",
    "movie_night": "Movie / TV time",
    "prayer_time": "Prayer / meditation",
}


class OnboardingService:
    """
    Converts an OnboardingPayload into graph nodes + edges and
    writes them to DynamoDB.
    """

    def __init__(self):
        self._table = get_table("household_graph")

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def build_graph(self, household_id: str, payload: "OnboardingPayload") -> dict:
        """
        Pure builder — returns nodes + edges WITHOUT writing to DynamoDB.
        Used by /onboarding/preview.
        """
        nodes, edges = self._build(household_id, payload)
        return {"nodes": nodes, "edges": edges}

    def create_household(self, household_id: str, payload: "OnboardingPayload") -> dict:
        """
        Write all nodes + edges to DynamoDB.
        Returns summary with counts.
        """
        nodes, edges = self._build(household_id, payload)
        self._write(household_id, payload, nodes, edges)
        member_ids = [n["node_id"] for n in nodes if n["node_type"] == "member"]
        device_ids = [n["node_id"] for n in nodes if n["node_type"] == "device"]
        routine_ids = [n["node_id"] for n in nodes if n["node_type"] == "routine"]
        logger.info(
            f"OnboardingService: created household {household_id} "
            f"nodes={len(nodes)} edges={len(edges)}"
        )
        return {
            "household_id": household_id,
            "created_nodes": len(nodes),
            "created_edges": len(edges),
            "member_node_ids": member_ids,
            "device_node_ids": device_ids,
            "routine_node_ids": routine_ids,
        }

    # ─────────────────────────────────────────────────────────
    # Internal builder
    # ─────────────────────────────────────────────────────────

    def _build(self, household_id: str, payload: "OnboardingPayload"):
        """Returns (nodes_list, edges_list) — pure, no I/O."""
        from schemas.onboarding import OnboardingPayload  # local import avoids circular

        nodes: list[dict] = []
        edges: list[dict] = []

        # ── Members ───────────────────────────────────────────
        member_id_map: dict[str, str] = {}  # client_id → node_id
        for i, m in enumerate(payload.members, start=1):
            node_id = f"mbr_{_slug(m.name)}_{i:03d}"
            member_id_map[m.id] = node_id
            nodes.append({
                "node_id": node_id,
                "node_type": "member",
                "name": m.name,
                "role": m.role,
                "age_group": m.age_group,
                "age": _AGE_GROUP_MIDPOINT.get(m.age_group, 30),
                "notification_channel": _ROLE_CHANNEL.get(m.role, "mobile_push"),
                "language": "english",  # default; user didn't specify
                "care_needs": m.care_needs,
            })

        # ── Devices ───────────────────────────────────────────
        device_id_map: dict[str, str] = {}  # client_id → node_id
        # Count per type to avoid duplicate node_ids
        device_type_counters: dict[str, int] = {}
        for d in payload.devices:
            dt = d.device_type
            device_type_counters[dt] = device_type_counters.get(dt, 0) + 1
            seq = device_type_counters[dt]
            node_id = f"dev_{_slug(dt)}_{seq:03d}"
            device_id_map[d.id] = node_id
            nodes.append({
                "node_id": node_id,
                "node_type": "device",
                "name": d.name,
                "device_type": _DEVICE_TYPE_MAP.get(dt, "other"),
                "room": _slug(d.room),
                "primary_user": None,  # assigned via edge below
            })

        # ── Routines ──────────────────────────────────────────
        routine_id_map: dict[str, str] = {}  # routine.id → node_id
        for i, r in enumerate(payload.routines, start=1):
            node_id = f"rtn_{_slug(r.id)}_{i:03d}"
            routine_id_map[r.id] = node_id
            nodes.append({
                "node_id": node_id,
                "node_type": "routine",
                "description": r.label or _ROUTINE_DESCRIPTIONS.get(r.id, r.id),
                "time_window": f"{r.time}-{r.time}" if r.time else None,
                "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            })

        # ── Edges ─────────────────────────────────────────────

        # 1. Device LOCATED_IN room
        for d in payload.devices:
            dev_nid = device_id_map.get(d.id)
            if dev_nid:
                edges.append({
                    "from": dev_nid,
                    "type": "LOCATED_IN",
                    "to": _slug(d.room),
                })

        # 2. Member PRIMARY_USER_OF first device in their room
        #    Heuristic: first member (owner/partner) gets primary user of all devices
        #    in rooms matching their sleep room (we don't have room per member in onboarding)
        #    → We assign primary user by order: owner gets device 0, partner gets device 1, etc.
        #    This is best-effort — user can edit later.
        owner_member = next(
            (member_id_map[m.id] for m in payload.members if m.role == "owner"),
            member_id_map.get(payload.members[0].id) if payload.members else None,
        )
        for d in payload.devices:
            dev_nid = device_id_map.get(d.id)
            if dev_nid and owner_member:
                edges.append({
                    "from": owner_member,
                    "type": "PRIMARY_USER_OF",
                    "to": dev_nid,
                })

        # 3. Member FOLLOWS routine — assign based on care_needs / time hints
        #    All members "follow" household routines (medicine goes to seniors)
        medicine_routines = {"medicine_morning", "medicine_night"}
        kids_routines = {"school_run", "homework_reminders"}
        # Find senior members for medicine
        senior_members = [
            member_id_map[m.id] for m in payload.members
            if m.age_group == "senior" or m.role == "grandparent"
        ]
        child_members = [
            member_id_map[m.id] for m in payload.members
            if m.age_group in ("child", "teen")
        ]
        all_member_ids = list(member_id_map.values())

        for r in payload.routines:
            rtn_nid = routine_id_map.get(r.id)
            if not rtn_nid:
                continue

            if r.id in medicine_routines:
                assignees = senior_members or all_member_ids[:1]
            elif r.id in kids_routines:
                assignees = child_members or all_member_ids[:1]
            else:
                # Generic household routine — assign to all members
                assignees = all_member_ids

            for mbr_nid in assignees:
                edges.append({
                    "from": mbr_nid,
                    "type": "FOLLOWS",
                    "to": rtn_nid,
                })

        # 4. Care needs → implicit health priority edges
        #    e.g. if a senior has "medicine_reminders", add a care edge
        for m in payload.members:
            mbr_nid = member_id_map.get(m.id)
            if not mbr_nid:
                continue
            for need in m.care_needs:
                edges.append({
                    "from": mbr_nid,
                    "type": "NEEDS_CARE",
                    "to": f"care_{_slug(need)}",
                    "care_type": need,
                })

        return nodes, edges

    # ─────────────────────────────────────────────────────────
    # DynamoDB writer
    # ─────────────────────────────────────────────────────────

    def _write(
        self,
        household_id: str,
        payload: "OnboardingPayload",
        nodes: list[dict],
        edges: list[dict],
    ) -> None:
        pk = f"HOUSEHOLD#{household_id}"
        now = datetime.now(timezone.utc).isoformat()

        with self._table.batch_writer() as batch:
            # META record
            batch.put_item(Item=_floats_to_decimal({
                "PK": pk,
                "SK": "META#household",
                "household_id": household_id,
                "family_name": payload.household_name,
                "location": payload.household_city,
                "node_type": "household",
                "graph_version": 1,
                "created_via": "onboarding",
                "created_at": now,
                "updated_at": now,
            }))

            # Nodes
            for node in nodes:
                item = _floats_to_decimal({
                    "PK": pk,
                    "SK": f"NODE#{node['node_id']}",
                    "household_id": household_id,
                    "created_at": now,
                    **node,
                })
                # Remove None values — DynamoDB rejects None
                item = {k: v for k, v in item.items() if v is not None}
                batch.put_item(Item=item)

            # Edges
            for edge in edges:
                sk = f"EDGE#{edge['from']}#{edge['type']}#{edge['to']}"
                item = _floats_to_decimal({
                    "PK": pk,
                    "SK": sk,
                    "from_node": edge["from"],
                    "edge_type": edge["type"],
                    "to_node": edge["to"],
                    "household_id": household_id,
                    "created_at": now,
                    **{k: v for k, v in edge.items() if k not in ("from", "type", "to")},
                })
                item = {k: v for k, v in item.items() if v is not None}
                batch.put_item(Item=item)

        logger.info(
            f"OnboardingService._write: wrote {len(nodes)} nodes + "
            f"{len(edges)} edges for {household_id}"
        )
