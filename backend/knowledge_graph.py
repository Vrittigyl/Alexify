"""
knowledge_graph.py
High-level query layer on top of GraphRepository + NetworkX.
Implements the 4 canonical graph queries used by the RTE and Bedrock context builder.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from graph_repository import GraphRepository

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """
    Wraps GraphRepository and exposes 4 domain-specific graph queries:
      Q1: get_affected_members_with_constraints()
      Q2: get_routine_conflicts_in_window()
      Q3: get_medications_due()
      Q4: get_device_impact()
    """

    def __init__(self, graph_repo: GraphRepository):
        self._repo = graph_repo

    def _graph(self, household_id: str) -> nx.DiGraph:
        return self._repo.load_graph(household_id)

    # ─────────────────────────────────────────────────────────────
    # Q1: get_affected_members_with_constraints()
    # ─────────────────────────────────────────────────────────────

    def get_affected_members_with_constraints(
        self,
        household_id: str,
        life_event_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        For each life event, return the members it DIRECTLY_AFFECTS along
        with any constraints from the life event node.

        Returns: [{"member_id": ..., "member_name": ..., "constraints": [...], "impact": ...}]
        """
        g = self._graph(household_id)
        results = []
        seen = set()

        for le_id in life_event_ids:
            if le_id not in g:
                continue
            le_attrs = g.nodes[le_id]

            for _, neighbor, edge_data in g.out_edges(le_id, data=True):
                if edge_data.get("edge_type") != "DIRECTLY_AFFECTS":
                    continue
                member_id = neighbor
                if member_id in seen:
                    continue
                seen.add(member_id)

                member_attrs = g.nodes.get(member_id, {})
                results.append({
                    "member_id": member_id,
                    "member_name": member_attrs.get("name", member_id),
                    "impact": edge_data.get("impact", "medium"),
                    "constraints": le_attrs.get("constraints", []),
                    "life_event": le_id,
                })

        return results

    # ─────────────────────────────────────────────────────────────
    # Q2: get_routine_conflicts_in_window()
    # ─────────────────────────────────────────────────────────────

    def get_routine_conflicts_in_window(
        self,
        household_id: str,
        time_window: str,
        member_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find routines that are active in a given time window and have CONFLICTS_WITH edges.
        time_window format: "HH:MM-HH:MM" e.g. "18:00-21:00"

        Returns: [{"routine_id": ..., "conflicts_with": ..., "reason": ..., "member_id": ...}]
        """
        g = self._graph(household_id)
        conflicts = []

        try:
            window_start, window_end = time_window.split("-")
        except ValueError:
            logger.warning(f"Invalid time_window format: {time_window}")
            return []

        for node_id, attrs in g.nodes(data=True):
            if attrs.get("node_type") != "routine":
                continue
            if member_ids and attrs.get("member_id") not in member_ids:
                continue

            rtn_window = attrs.get("time_window", "")
            if not rtn_window:
                continue

            # Check overlap: routine window overlaps with query window
            try:
                r_start, r_end = rtn_window.split("-")
            except ValueError:
                continue

            if r_start < window_end and r_end > window_start:
                # This routine is active in the window — check for CONFLICTS_WITH
                for _, conflict_target, edge_data in g.out_edges(node_id, data=True):
                    if edge_data.get("edge_type") == "CONFLICTS_WITH":
                        conflicts.append({
                            "routine_id": node_id,
                            "routine_description": attrs.get("description", ""),
                            "member_id": attrs.get("member_id"),
                            "conflicts_with": conflict_target,
                            "reason": edge_data.get("reason", ""),
                            "time_window": rtn_window,
                        })

        return conflicts

    # ─────────────────────────────────────────────────────────────
    # Q3: get_medications_due()
    # ─────────────────────────────────────────────────────────────

    def get_medications_due(
        self,
        household_id: str,
        member_ids: list[str],
        window_start: str,
        window_end: str,
    ) -> list[dict[str, Any]]:
        """
        Return medications due for the given members within the time window.
        window_start / window_end: "HH:MM" strings.

        Returns: [{"member_id": ..., "member_name": ..., "medication_id": ...,
                   "medication_name": ..., "schedule": ..., "critical": bool}]
        """
        g = self._graph(household_id)
        due = []

        for member_id in member_ids:
            if member_id not in g:
                continue
            member_name = g.nodes[member_id].get("name", member_id)

            for _, med_id, edge_data in g.out_edges(member_id, data=True):
                if edge_data.get("edge_type") != "TAKES":
                    continue

                med_attrs = g.nodes.get(med_id, {})
                schedule = edge_data.get("schedule") or med_attrs.get("schedule", "")

                # Check if schedule falls within the window
                if schedule and window_start <= schedule <= window_end:
                    due.append({
                        "member_id": member_id,
                        "member_name": member_name,
                        "medication_id": med_id,
                        "medication_name": med_attrs.get("name", med_id),
                        "schedule": schedule,
                        "critical": med_attrs.get("critical", False),
                    })

        # Sort by schedule time
        due.sort(key=lambda x: x["schedule"])
        return due

    # ─────────────────────────────────────────────────────────────
    # Q4: get_device_impact()
    # ─────────────────────────────────────────────────────────────

    def get_device_impact(
        self,
        household_id: str,
        device_id: str,
    ) -> dict[str, Any]:
        """
        For a given device, return:
        - Primary user
        - Room location
        - Members who CONFLICTS_WITH this device (e.g. Dadaji's arthritis vs AC)
        - Routines that use this device

        Returns a dict with primary_user, room, conflicts, routines.
        """
        g = self._graph(household_id)

        if device_id not in g:
            return {"device_id": device_id, "found": False}

        device_attrs = g.nodes[device_id]
        primary_user = None
        room = None
        conflicts = []
        routines_using = []

        # Find all edges pointing TO this device
        for source, _, edge_data in g.in_edges(device_id, data=True):
            etype = edge_data.get("edge_type")
            if etype == "PRIMARY_USER_OF":
                member_attrs = g.nodes.get(source, {})
                primary_user = {
                    "member_id": source,
                    "member_name": member_attrs.get("name", source),
                }
            elif etype == "CONFLICTS_WITH":
                source_attrs = g.nodes.get(source, {})
                conflicts.append({
                    "from_node": source,
                    "from_type": source_attrs.get("node_type", "unknown"),
                    "reason": edge_data.get("reason", ""),
                })

        # Find room (LOCATED_IN edge from device)
        for _, target, edge_data in g.out_edges(device_id, data=True):
            if edge_data.get("edge_type") == "LOCATED_IN":
                room = target

        # Find routines that CONFLICTS_WITH this device (already done via in_edges)
        # Also find any routines whose time window overlaps with device usage
        for node_id, attrs in g.nodes(data=True):
            if attrs.get("node_type") == "routine":
                for _, conflict_target, edge_data in g.out_edges(node_id, data=True):
                    if edge_data.get("edge_type") == "CONFLICTS_WITH" and conflict_target == device_id:
                        routines_using.append({
                            "routine_id": node_id,
                            "description": attrs.get("description", ""),
                            "member_id": attrs.get("member_id"),
                            "reason": edge_data.get("reason", ""),
                        })

        return {
            "device_id": device_id,
            "device_type": device_attrs.get("device_type"),
            "device_name": device_attrs.get("name"),
            "found": True,
            "primary_user": primary_user,
            "room": room,
            "conflicts": conflicts,
            "routine_conflicts": routines_using,
        }

    def get_subgraph_for_bedrock(
        self,
        household_id: str,
        member_ids: list[str],
        device_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build a targeted subgraph for Bedrock context.
        Only includes nodes/edges relevant to the given members and devices.
        This keeps token count low.
        """
        g = self._graph(household_id)
        relevant_nodes = set(member_ids)
        if device_ids:
            relevant_nodes.update(device_ids)

        # Expand one hop: health conditions, medications, routines
        for node in list(relevant_nodes):
            if node not in g:
                continue
            for _, neighbor, edge_data in g.out_edges(node, data=True):
                etype = edge_data.get("edge_type", "")
                if etype in ("HAS_CONDITION", "TAKES", "FOLLOWS", "PRIMARY_USER_OF"):
                    relevant_nodes.add(neighbor)

        subgraph = g.subgraph(relevant_nodes)
        return {
            "nodes": [
                {"id": n, **{k: v for k, v in d.items() if k not in ("PK", "SK")}}
                for n, d in subgraph.nodes(data=True)
            ],
            "edges": [
                {"from": u, "type": d.get("edge_type"), "to": v}
                for u, v, d in subgraph.edges(data=True)
            ],
            "node_count": subgraph.number_of_nodes(),
            "edge_count": subgraph.number_of_edges(),
        }
