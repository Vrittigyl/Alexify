"""
db/seed_dynamo.py
Creates all 7 DynamoDB tables and seeds them with Sharma family data.
Run directly: python db/seed_dynamo.py
Or via the API: POST /admin/seed
"""

import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import settings

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


# ─────────────────────────────────────────────────────────────
# Table definitions
# ─────────────────────────────────────────────────────────────

TABLE_DEFINITIONS = [
    {
        "TableName": settings.table_household_graph,
        "KeySchema": [
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.table_household_rules,
        "KeySchema": [
            {"AttributeName": "household_id", "KeyType": "HASH"},
            {"AttributeName": "rule_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "household_id", "AttributeType": "S"},
            {"AttributeName": "rule_id", "AttributeType": "S"},
            {"AttributeName": "rule_type", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "rule_type-index",
                "KeySchema": [
                    {"AttributeName": "rule_type", "KeyType": "HASH"},
                    {"AttributeName": "rule_id", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.table_household_patterns,
        "KeySchema": [
            {"AttributeName": "household_id", "KeyType": "HASH"},
            {"AttributeName": "pattern_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "household_id", "AttributeType": "S"},
            {"AttributeName": "pattern_id", "AttributeType": "S"},
            {"AttributeName": "confidence_band", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "confidence_band-index",
                "KeySchema": [
                    {"AttributeName": "confidence_band", "KeyType": "HASH"},
                    {"AttributeName": "pattern_id", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.table_rte_audit_log,
        "KeySchema": [
            {"AttributeName": "event_id", "KeyType": "HASH"},
            {"AttributeName": "timestamp", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "event_id", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "S"},
            {"AttributeName": "household_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "household_id-index",
                "KeySchema": [
                    {"AttributeName": "household_id", "KeyType": "HASH"},
                    {"AttributeName": "timestamp", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.table_household_metrics,
        "KeySchema": [
            {"AttributeName": "household_id", "KeyType": "HASH"},
            {"AttributeName": "date", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "household_id", "AttributeType": "S"},
            {"AttributeName": "date", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.table_action_log,
        "KeySchema": [
            {"AttributeName": "action_id", "KeyType": "HASH"},
            {"AttributeName": "created_at", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "action_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
            {"AttributeName": "household_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "household_id-index",
                "KeySchema": [
                    {"AttributeName": "household_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.table_conflict_audit_log,
        "KeySchema": [
            {"AttributeName": "conflict_id", "KeyType": "HASH"},
            {"AttributeName": "timestamp", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "conflict_id", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _floats_to_decimal(obj):
    """DynamoDB doesn't accept float — convert to Decimal recursively."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimal(i) for i in obj]
    return obj


def _get_client():
    _cfg = Config(
        retries={"max_attempts": settings.DYNAMO_MAX_ATTEMPTS, "mode": "adaptive"},
        connect_timeout=settings.DYNAMO_CONNECT_TIMEOUT,
        read_timeout=settings.DYNAMO_READ_TIMEOUT,
    )
    return boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        config=_cfg,
    )


def _get_resource():
    _cfg = Config(
        retries={"max_attempts": settings.DYNAMO_MAX_ATTEMPTS, "mode": "adaptive"},
        connect_timeout=settings.DYNAMO_CONNECT_TIMEOUT,
        read_timeout=settings.DYNAMO_READ_TIMEOUT,
    )
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        config=_cfg,
    )


# ─────────────────────────────────────────────────────────────
# 4.1  create_tables()
# ─────────────────────────────────────────────────────────────

def create_tables() -> dict:
    """
    Create all 7 DynamoDB tables.
    Skips tables that already exist (safe to re-run).
    Returns a summary of created vs skipped tables.
    """
    client = _get_client()
    created = []
    skipped = []

    for defn in TABLE_DEFINITIONS:
        table_name = defn["TableName"]
        try:
            client.create_table(**defn)
            logger.info(f"Created table: {table_name}")
            created.append(table_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                logger.info(f"Table already exists (skipped): {table_name}")
                skipped.append(table_name)
            else:
                raise

    # Wait for all newly created tables to become ACTIVE
    if created:
        logger.info(f"Waiting for {len(created)} tables to become ACTIVE...")
        resource = _get_resource()
        for table_name in created:
            resource.Table(table_name).wait_until_exists()
            logger.info(f"  {table_name} is ACTIVE")

        # Enable PITR on each newly created table
        # PITR allows point-in-time recovery for up to 35 days
        logger.info("Enabling Point-In-Time Recovery on all new tables...")
        for table_name in created:
            try:
                client.update_continuous_backups(
                    TableName=table_name,
                    PointInTimeRecoverySpecification={
                        "PointInTimeRecoveryEnabled": True
                    },
                )
                logger.info(f"  PITR enabled: {table_name}")
            except ClientError as e:
                # Local DynamoDB (DynamoDB Local) does not support PITR— soft-fail
                logger.warning(f"  PITR not available for {table_name}: {e.response['Error']['Code']}")

    return {"created": created, "skipped": skipped}


# ─────────────────────────────────────────────────────────────
# 4.2  seed_household_graph()
# ─────────────────────────────────────────────────────────────

def seed_household_graph() -> int:
    """
    Write all nodes and edges from sharma_family.json to HouseholdGraph.
    Uses DynamoDB adjacency list pattern:
      - Nodes: PK=HOUSEHOLD#<hh_id>, SK=NODE#<node_id>
      - Edges: PK=HOUSEHOLD#<hh_id>, SK=EDGE#<from>#<type>#<to>
    Returns total items written.
    """
    with open(DATA_DIR / "sharma_family.json", encoding="utf-8") as f:
        family = json.load(f)

    resource = _get_resource()
    table = resource.Table(settings.table_household_graph)
    hh_id = family["household_id"]
    pk = f"HOUSEHOLD#{hh_id}"

    count = 0
    with table.batch_writer() as batch:
        # Write household metadata
        batch.put_item(Item={
            "PK": pk,
            "SK": "META#household",
            "household_id": hh_id,
            "family_name": family["family_name"],
            "location": family["location"],
            "node_type": "household",
            "graph_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        count += 1

        # Write all node types
        node_categories = [
            ("members", "member"),
            ("devices", "device"),
            ("health_conditions", "health_condition"),
            ("medications", "medication"),
            ("routines", "routine"),
            ("life_events", "life_event"),
        ]
        for category, node_type in node_categories:
            for node in family["nodes"][category]:
                item = _floats_to_decimal({
                    "PK": pk,
                    "SK": f"NODE#{node['node_id']}",
                    "node_id": node["node_id"],
                    "node_type": node_type,
                    "household_id": hh_id,
                    **node,
                })
                batch.put_item(Item=item)
                count += 1

        # Write all edges
        for edge in family["edges"]:
            item = _floats_to_decimal({
                "PK": pk,
                "SK": f"EDGE#{edge['from']}#{edge['type']}#{edge['to']}",
                "from_node": edge["from"],
                "edge_type": edge["type"],
                "to_node": edge["to"],
                "household_id": hh_id,
                **{k: v for k, v in edge.items() if k not in ("from", "type", "to")},
            })
            batch.put_item(Item=item)
            count += 1

    logger.info(f"HouseholdGraph seeded: {count} items written")
    return count


# ─────────────────────────────────────────────────────────────
# 4.3  seed_rules()
# ─────────────────────────────────────────────────────────────

def seed_rules() -> int:
    """
    Write all rules from fleet_rules.json to HouseholdRules.
    FLEET rules keep household_id='FLEET'.
    Returns total rules written.
    """
    with open(DATA_DIR / "fleet_rules.json", encoding="utf-8") as f:
        rules = json.load(f)

    resource = _get_resource()
    table = resource.Table(settings.table_household_rules)

    count = 0
    with table.batch_writer() as batch:
        for rule in rules:
            item = _floats_to_decimal({
                **rule,
                "seeded_at": datetime.now(timezone.utc).isoformat(),
            })
            batch.put_item(Item=item)
            count += 1

    logger.info(f"HouseholdRules seeded: {count} rules written")
    return count


# ─────────────────────────────────────────────────────────────
# 4.4  seed_patterns()
# ─────────────────────────────────────────────────────────────

def seed_patterns() -> int:
    """
    Write all patterns from patterns_seed.json to HouseholdPatterns.
    Returns total patterns written.
    """
    with open(DATA_DIR / "patterns_seed.json", encoding="utf-8") as f:
        patterns = json.load(f)

    resource = _get_resource()
    table = resource.Table(settings.table_household_patterns)

    count = 0
    with table.batch_writer() as batch:
        for pattern in patterns:
            item = _floats_to_decimal({
                **pattern,
                "seeded_at": datetime.now(timezone.utc).isoformat(),
            })
            batch.put_item(Item=item)
            count += 1

    logger.info(f"HouseholdPatterns seeded: {count} patterns written")
    return count


# ─────────────────────────────────────────────────────────────
# 4.5  verify_seeding()
# ─────────────────────────────────────────────────────────────

def verify_seeding() -> dict:
    """
    Scan each table and report record counts.
    Also spot-checks a few critical records.
    """
    resource = _get_resource()
    results = {}

    checks = [
        ("HouseholdGraph",    settings.table_household_graph),
        ("HouseholdRules",    settings.table_household_rules),
        ("HouseholdPatterns", settings.table_household_patterns),
        ("RTEAuditLog",       settings.table_rte_audit_log),
        ("HouseholdMetrics",  settings.table_household_metrics),
        ("ActionLog",         settings.table_action_log),
        ("ConflictAuditLog",  settings.table_conflict_audit_log),
    ]

    for label, table_name in checks:
        table = resource.Table(table_name)
        resp = table.scan(Select="COUNT")
        count = resp["Count"]
        results[label] = count
        logger.info(f"  {label:25s}: {count:4d} records")

    # Spot-check: Dadaji node must exist
    graph_table = resource.Table(settings.table_household_graph)
    resp = graph_table.get_item(Key={
        "PK": "HOUSEHOLD#hh_xk92p_sharma",
        "SK": "NODE#mbr_dadaji_001",
    })
    dadaji_ok = "Item" in resp
    results["spot_check_dadaji_node"] = dadaji_ok

    # Spot-check: water motor safety rule must exist
    rules_table = resource.Table(settings.table_household_rules)
    resp = rules_table.get_item(Key={
        "household_id": "FLEET",
        "rule_id": "rl_water_motor_tank_full",
    })
    rule_ok = "Item" in resp
    results["spot_check_safety_rule"] = rule_ok

    # Spot-check: promoted pattern must exist
    patterns_table = resource.Table(settings.table_household_patterns)
    resp = patterns_table.get_item(Key={
        "household_id": "hh_xk92p_sharma",
        "pattern_id": "ptn_dadaji_medicine_evening",
    })
    pattern_ok = "Item" in resp
    results["spot_check_promoted_pattern"] = pattern_ok

    all_ok = dadaji_ok and rule_ok and pattern_ok
    results["all_spot_checks_passed"] = all_ok
    logger.info(f"  Spot checks: {'PASS' if all_ok else 'FAIL'}")

    return results


# ─────────────────────────────────────────────────────────────
# Main — run all steps in sequence
# ─────────────────────────────────────────────────────────────

def run_full_seed() -> dict:
    """Run all seeding steps and return a combined summary."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )

    logger.info("=" * 60)
    logger.info("SAATHI — DynamoDB Seeding")
    logger.info("=" * 60)

    logger.info("\n[1] Creating tables...")
    tables = create_tables()

    logger.info("\n[2] Seeding HouseholdGraph...")
    graph_count = seed_household_graph()

    logger.info("\n[3] Seeding HouseholdRules...")
    rules_count = seed_rules()

    logger.info("\n[4] Seeding HouseholdPatterns...")
    patterns_count = seed_patterns()

    logger.info("\n[5] Verifying seeding...")
    verification = verify_seeding()

    summary = {
        "tables_created": tables["created"],
        "tables_skipped": tables["skipped"],
        "graph_items": graph_count,
        "rules": rules_count,
        "patterns": patterns_count,
        "verification": verification,
    }

    logger.info("\n" + "=" * 60)
    logger.info("Seeding complete.")
    logger.info(f"  Graph items : {graph_count}")
    logger.info(f"  Rules       : {rules_count}")
    logger.info(f"  Patterns    : {patterns_count}")
    logger.info(f"  Spot checks : {'PASS' if verification['all_spot_checks_passed'] else 'FAIL'}")
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    run_full_seed()
