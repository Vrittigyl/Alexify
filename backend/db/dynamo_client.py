"""
db/dynamo_client.py — DynamoDB Client
Centralised boto3 DynamoDB resource.
All table access goes through get_table() — never create boto3 resources elsewhere.
Connection is verified on startup via health_check().
"""

import boto3
import logging
from botocore.exceptions import ClientError, NoCredentialsError, EndpointResolutionError
from config import settings

logger = logging.getLogger(__name__)

# Single boto3 resource (module-level, reused across all calls) 
_dynamodb = boto3.resource(
    "dynamodb",
    region_name=settings.aws_region,
    aws_access_key_id=settings.aws_access_key_id or None,
    aws_secret_access_key=settings.aws_secret_access_key or None,
)

# All 7 table names from config
TABLE_NAMES = {
    "household_graph":    settings.table_household_graph,
    "household_rules":    settings.table_household_rules,
    "household_patterns": settings.table_household_patterns,
    "rte_audit_log":      settings.table_rte_audit_log,
    "household_metrics":  settings.table_household_metrics,
    "action_log":         settings.table_action_log,
    "conflict_audit_log": settings.table_conflict_audit_log,
}


def get_table(name: str):
    """
    Return a DynamoDB Table resource by logical name.

    Args:
        name: Logical table key (e.g. 'household_graph', 'rte_audit_log')
              OR the raw DynamoDB table name string.

    Returns:
        boto3 DynamoDB Table resource
    """
    table_name = TABLE_NAMES.get(name, name)
    return _dynamodb.Table(table_name)


def get_resource():
    """Return the raw boto3 DynamoDB resource (for create_table operations)."""
    return _dynamodb


def health_check() -> dict:
    """
    Verify DynamoDB connectivity by listing tables.
    Called on application startup.

    Returns:
        dict with status ('connected' | 'unavailable'), region, and details
    """
    try:
        client = boto3.client(
            "dynamodb",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        response = client.list_tables(Limit=1)
        logger.info(f"DynamoDB connected — region: {settings.aws_region}")
        return {
            "status": "connected",
            "region": settings.aws_region,
            "table_count_sample": len(response.get("TableNames", [])),
        }
    except NoCredentialsError:
        logger.warning("DynamoDB: No AWS credentials found — running in offline mode")
        return {
            "status": "no_credentials",
            "region": settings.aws_region,
            "detail": "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env",
        }
    except (ClientError, EndpointResolutionError, Exception) as e:
        logger.warning(f"DynamoDB unavailable: {e}")
        return {
            "status": "unavailable",
            "region": settings.aws_region,
            "detail": str(e),
        }
