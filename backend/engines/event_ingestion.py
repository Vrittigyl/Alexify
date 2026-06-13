"""
event_ingestion.py
Entry point for all raw device events.
Pipeline: adapter lookup → normalize → bloom dedup → return NormalizedEvent | None
"""

import hashlib
import logging
import time
from typing import Any

from schemas import NormalizedEvent
from schemas.enums import DeviceType, EventType
from adapters.adapter_registry import get_adapter

logger = logging.getLogger(__name__)

# In-process bloom filter substitute using a dict with TTL timestamps.
# Keyed by dedup_key, value is expiry timestamp (epoch seconds).
# For production this would be Redis, but for the hackathon this is sufficient.
_dedup_cache: dict[str, float] = {}
_DEDUP_TTL_SECS = 60  # 1 minute window


def _is_duplicate(dedup_key: str) -> bool:
    """Check if this dedup_key was seen within the TTL window."""
    now = time.time()
    expiry = _dedup_cache.get(dedup_key)
    if expiry and expiry > now:
        return True
    return False


def _mark_seen(dedup_key: str) -> None:
    """Register this dedup_key. Prune stale entries opportunistically."""
    now = time.time()
    _dedup_cache[dedup_key] = now + _DEDUP_TTL_SECS

    # Prune expired entries every ~100 calls to keep memory bounded
    if len(_dedup_cache) % 100 == 0:
        expired = [k for k, v in _dedup_cache.items() if v <= now]
        for k in expired:
            del _dedup_cache[k]


def ingest(
    raw_payload: dict[str, Any],
    device_type: str | DeviceType,
    household_id: str,
    device_id: str,
    room_id: str | None = None,
    affected_member_ids: list[str] | None = None,
) -> NormalizedEvent | None:
    """
    Normalize a raw device payload into a NormalizedEvent.

    Returns None if:
    - No adapter is registered for this device_type
    - The event is a duplicate within the dedup window

    Callers should treat None as "no action needed".
    """
    adapter = get_adapter(device_type)
    if adapter is None:
        logger.warning(f"No adapter registered for device_type={device_type!r} — skipping")
        return None

    event = adapter.normalize(
        raw_payload=raw_payload,
        household_id=household_id,
        device_id=device_id,
        room_id=room_id,
        affected_member_ids=affected_member_ids,
    )

    # Dedup check
    if event.dedup_key and _is_duplicate(event.dedup_key):
        logger.debug(f"Duplicate event suppressed: dedup_key={event.dedup_key}")
        return None

    if event.dedup_key:
        _mark_seen(event.dedup_key)

    logger.info(
        f"Event ingested: {event.event_id} | "
        f"household={household_id} | "
        f"device={device_id} | "
        f"type={event.event_type.value} | "
        f"impact={event.impact_level.value}"
    )
    return event


def ingest_life_event(
    event_type: EventType,
    household_id: str,
    payload: dict[str, Any],
    affected_member_ids: list[str] | None = None,
    requires_ai: bool = True,
) -> NormalizedEvent:
    """
    Ingest non-device events (guest arrivals, life events, schedule triggers, etc.).
    These always bypass the adapter layer and always route to Bedrock.
    """
    from datetime import datetime, timezone

    event = NormalizedEvent(
        household_id=household_id,
        event_type=event_type,
        device_type=None,
        device_id=None,
        payload=payload,
        affected_member_ids=affected_member_ids or [],
        requires_ai=requires_ai,
        adapter_id="life_event_v1",
    )

    logger.info(
        f"Life event ingested: {event.event_id} | "
        f"type={event_type.value} | "
        f"household={household_id}"
    )
    return event
