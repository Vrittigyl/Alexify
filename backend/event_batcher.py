"""
event_batcher.py — Phase 9.3
==============================
Per-household event buffer that collects events into batches before
sending to Bedrock. This prevents hammering Bedrock with every event.

Rules:
  - 10-minute rolling window per household (deque of events)
  - Immediate flush on CRITICAL impact events
  - Auto-flush when batch reaches 15 events
  - Within-batch dedup: same (device_id, event_type) within 2 minutes → discard duplicate
"""

import logging
import time
from collections import deque
from typing import Any

from config import settings
from schemas import NormalizedEvent
from schemas.enums import ImpactLevel

logger = logging.getLogger(__name__)

# Within-batch dedup window (same device+event_type)
_DEDUP_WINDOW_SECS = 120


class EventBatcher:
    """
    Per-household sliding-window event buffer.
    Thread-safe for single-process use (CPython GIL).
    """

    def __init__(
        self,
        window_mins: int | None = None,
        max_batch_size: int | None = None,
    ):
        self._window_secs = (window_mins or settings.batcher_window_mins) * 60
        self._max_size = max_batch_size or settings.batcher_max_batch_size

        # household_id → deque of (event, added_at)
        self._batches: dict[str, deque] = {}
        # Dedup tracker: household_id → { dedup_key: last_seen_ts }
        self._seen: dict[str, dict[str, float]] = {}

    # ── Add ──────────────────────────────────────────────────

    def add(self, event: NormalizedEvent) -> bool:
        """
        Add an event to the household batch.
        Returns True if the event was added, False if deduped.
        Auto-flushes if batch hits CRITICAL or max_size.
        """
        hh = event.household_id
        now = time.monotonic()

        # Within-batch dedup
        dedup_key = f"{event.device_id}:{event.event_type.value}"
        seen_at = self._seen.setdefault(hh, {}).get(dedup_key, 0)
        if (now - seen_at) < _DEDUP_WINDOW_SECS:
            logger.debug(f"Batcher dedup: {dedup_key} suppressed for {hh}")
            return False

        self._seen[hh][dedup_key] = now

        # Ensure deque exists
        if hh not in self._batches:
            self._batches[hh] = deque()

        # Evict expired entries from window
        self._evict_expired(hh, now)

        self._batches[hh].append((event, now))
        logger.debug(f"Batcher add: {event.event_id} | household={hh} | size={len(self._batches[hh])}")

        return True

    def should_flush(self, household_id: str, event: NormalizedEvent) -> bool:
        """Return True if this event should trigger an immediate Bedrock call."""
        batch = self._batches.get(household_id, deque())
        if len(batch) >= self._max_size:
            logger.info(f"Batcher flush: max_size={self._max_size} reached for {household_id}")
            return True
        if event.impact_level == ImpactLevel.CRITICAL:
            logger.info(f"Batcher flush: CRITICAL event {event.event_id} for {household_id}")
            return True
        return False

    # ── Flush ────────────────────────────────────────────────

    def flush(self, household_id: str) -> list[NormalizedEvent]:
        """
        Return all buffered events for the household and clear the buffer.
        Also clears the dedup tracker so fresh events are accepted.
        """
        batch = self._batches.pop(household_id, deque())
        self._seen.pop(household_id, None)
        events = [ev for ev, _ in batch]
        logger.info(f"Batcher flushed: household={household_id} events={len(events)}")
        return events

    def get_batch(self, household_id: str) -> list[NormalizedEvent]:
        """Return current buffered events without clearing."""
        self._evict_expired(household_id, time.monotonic())
        return [ev for ev, _ in self._batches.get(household_id, deque())]

    def batch_size(self, household_id: str) -> int:
        self._evict_expired(household_id, time.monotonic())
        return len(self._batches.get(household_id, deque()))

    # ── Internals ────────────────────────────────────────────

    def _evict_expired(self, household_id: str, now: float) -> None:
        batch = self._batches.get(household_id)
        if not batch:
            return
        cutoff = now - self._window_secs
        while batch and batch[0][1] < cutoff:
            batch.popleft()
