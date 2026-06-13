"""
graph_repository.py
DynamoDB ↔ NetworkX bridge for the household knowledge graph.
All graph reads/writes go through this class.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
import networkx as nx
from boto3.dynamodb.conditions import Key

from config import settings
from db.dynamo_client import get_table
from schemas import Rule, PatternRecord
from schemas.enums import ConfidenceBand, RuleType

logger = logging.getLogger(__name__)


def _decimal_to_native(obj: Any) -> Any:
    """DynamoDB returns Decimals — convert back to int/float for normal use."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_native(i) for i in obj]
    return obj


def _floats_to_decimal(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimal(i) for i in obj]
    return obj


class GraphRepository:
    """
    Loads and manages the household knowledge graph.
    Internally uses NetworkX DiGraph for fast traversal.

    Graph is lazy-loaded and cached per household_id.
    Call invalidate_cache() or upsert_node/edge to mark it dirty.
    """

    def __init__(self):
        self._cache: dict[str, nx.DiGraph] = {}
        self._dirty: dict[str, bool] = {}
        self._graph_table = get_table("household_graph")
        self._rules_table = get_table("household_rules")
        self._patterns_table = get_table("household_patterns")

    # ─────────────────────────────────────────────────────────────
    # 6.1  load_graph()
    # ─────────────────────────────────────────────────────────────

    def load_graph(self, household_id: str, force_reload: bool = False) -> nx.DiGraph:
        """
        Load the household knowledge graph from DynamoDB into a NetworkX DiGraph.
        Result is cached — subsequent calls return the cached version unless
        force_reload=True or the graph has been marked dirty.
        """
        if household_id in self._cache and not force_reload and not self._dirty.get(household_id):
            return self._cache[household_id]

        pk = f"HOUSEHOLD#{household_id}"
        graph = nx.DiGraph()
        graph.graph["household_id"] = household_id

        # Paginate through all items for this household
        items = []
        kwargs = {
            "KeyConditionExpression": Key("PK").eq(pk),
        }
        while True:
            resp = self._graph_table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last

        nodes_loaded = 0
        edges_loaded = 0

        for item in items:
            item = _decimal_to_native(item)
            sk = item.get("SK", "")

            if sk.startswith("META#"):
                graph.graph["version"] = item.get("graph_version", 1)

            elif sk.startswith("NODE#"):
                node_id = item["node_id"]
                graph.add_node(node_id, **{k: v for k, v in item.items() if k not in ("PK", "SK")})
                nodes_loaded += 1

            elif sk.startswith("EDGE#"):
                from_node = item["from_node"]
                to_node = item["to_node"]
                edge_type = item["edge_type"]
                attrs = {k: v for k, v in item.items() if k not in ("PK", "SK", "from_node", "to_node", "edge_type")}
                # Nodes referenced in edges may be rooms (not NODE# items) — add them lazily
                if from_node not in graph:
                    graph.add_node(from_node)
                if to_node not in graph:
                    graph.add_node(to_node)
                graph.add_edge(from_node, to_node, edge_type=edge_type, **attrs)
                edges_loaded += 1

        logger.info(f"Graph loaded: household={household_id}, nodes={nodes_loaded}, edges={edges_loaded}")
        self._cache[household_id] = graph
        self._dirty[household_id] = False
        return graph

    # ─────────────────────────────────────────────────────────────
    # 6.2  get_graph_version()
    # ─────────────────────────────────────────────────────────────

    def get_graph_version(self, household_id: str) -> int:
        """Read graph_version from the household metadata node."""
        resp = self._graph_table.get_item(Key={
            "PK": f"HOUSEHOLD#{household_id}",
            "SK": "META#household",
        })
        item = resp.get("Item", {})
        return int(item.get("graph_version", 1))

    # ─────────────────────────────────────────────────────────────
    # 6.3  upsert_node() / upsert_edge()
    # ─────────────────────────────────────────────────────────────

    def upsert_node(self, household_id: str, node_id: str, node_type: str, attrs: dict[str, Any]) -> None:
        """Write/update a node in DynamoDB and mark the in-memory graph dirty."""
        item = _floats_to_decimal({
            "PK": f"HOUSEHOLD#{household_id}",
            "SK": f"NODE#{node_id}",
            "node_id": node_id,
            "node_type": node_type,
            "household_id": household_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **attrs,
        })
        self._graph_table.put_item(Item=item)
        self._dirty[household_id] = True
        logger.info(f"Node upserted: {node_id} (type={node_type})")

    def upsert_edge(
        self,
        household_id: str,
        from_node: str,
        edge_type: str,
        to_node: str,
        attrs: dict[str, Any] | None = None,
    ) -> None:
        """Write/update an edge in DynamoDB and mark the in-memory graph dirty."""
        item = _floats_to_decimal({
            "PK": f"HOUSEHOLD#{household_id}",
            "SK": f"EDGE#{from_node}#{edge_type}#{to_node}",
            "from_node": from_node,
            "edge_type": edge_type,
            "to_node": to_node,
            "household_id": household_id,
            **(attrs or {}),
        })
        self._graph_table.put_item(Item=item)
        self._dirty[household_id] = True
        logger.info(f"Edge upserted: {from_node} --{edge_type}--> {to_node}")

    # ─────────────────────────────────────────────────────────────
    # 6.4  promote_pattern_to_rule()
    # ─────────────────────────────────────────────────────────────

    def promote_pattern_to_rule(self, household_id: str, pattern_id: str) -> Rule | None:
        """
        Promote a LEARNING pattern to a Rule.
        - Reads the pattern from HouseholdPatterns
        - Builds a Rule from the pattern's metadata
        - Writes the rule to HouseholdRules
        - Updates pattern confidence_band to PROMOTED
        - Increments graph_version
        Returns the created Rule, or None if pattern not found / not eligible.
        """
        resp = self._patterns_table.get_item(Key={
            "household_id": household_id,
            "pattern_id": pattern_id,
        })
        item = resp.get("Item")
        if not item:
            logger.warning(f"Pattern not found: {pattern_id}")
            return None

        item = _decimal_to_native(item)
        confidence = float(item.get("confidence", 0))
        obs_days = int(item.get("observation_days", 0))
        band = item.get("confidence_band", "OBSERVING")

        if confidence < 0.90 or obs_days < 30:
            logger.warning(
                f"Pattern {pattern_id} not eligible for promotion: "
                f"confidence={confidence}, observation_days={obs_days}"
            )
            return None

        # Build rule from pattern
        rule_id = f"rl_promoted_{pattern_id}"
        rule = Rule(
            household_id=household_id,
            rule_id=rule_id,
            rule_type=RuleType.PROMOTED_PATTERN,
            rule_version=1,
            name=f"Promoted: {item.get('description', pattern_id)}",
            trigger={
                "event_type": item.get("event_type"),
                "device_type": item.get("device_type"),
            },
            action={"type": "notification", "message_template": f"Pattern triggered: {item.get('description', '')}"},
            source_pattern_id=pattern_id,
            observation_days=obs_days,
            original_confidence=confidence,
            demotion_trigger="3_consecutive_misses",
        )

        # Write rule
        self._rules_table.put_item(Item=_floats_to_decimal({
            **rule.model_dump(),
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }))

        # Update pattern band
        self._patterns_table.update_item(
            Key={"household_id": household_id, "pattern_id": pattern_id},
            UpdateExpression="SET confidence_band = :band, promoted_rule_id = :rid, promoted_at = :ts",
            ExpressionAttributeValues={
                ":band": ConfidenceBand.PROMOTED.value,
                ":rid": rule_id,
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Increment graph version
        self._graph_table.update_item(
            Key={"PK": f"HOUSEHOLD#{household_id}", "SK": "META#household"},
            UpdateExpression="SET graph_version = graph_version + :inc",
            ExpressionAttributeValues={":inc": 1},
        )

        self._dirty[household_id] = True
        logger.info(f"Pattern {pattern_id} promoted to rule {rule_id}")
        return rule

    def get_patterns(self, household_id: str, band: str | None = None) -> list[dict]:
        """
        Fetch all patterns for a household from HouseholdPatterns.
        Optionally filter by confidence_band.
        """
        kwargs = {
            "KeyConditionExpression": Key("household_id").eq(household_id),
        }
        items = []
        while True:
            resp = self._patterns_table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last

        result = [_decimal_to_native(item) for item in items]
        if band:
            result = [p for p in result if p.get("confidence_band") == band]
        return result

    def invalidate_cache(self, household_id: str) -> None:
        """Force next load_graph() call to re-fetch from DynamoDB."""
        self._dirty[household_id] = True
