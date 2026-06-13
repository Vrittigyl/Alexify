"""
presence_service.py — Phase 9.1
================================
In-memory presence tracker with TTL-based expiry.
Tracks which room each household member is in and whether they're home.

Key design:
  - Pure in-memory (dict) — intentionally ephemeral.
  - TTL-checked on every read, not on write (lazy eviction keeps write path fast).
  - Thread-safe via simple dict operations (CPython GIL is sufficient here).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class PresenceRecord:
    member_id: str
    room_id: Optional[str]
    is_home: bool
    updated_at: float = field(default_factory=time.monotonic)


class PresenceService:
    """
    In-memory TTL presence store.
    Key: household_id:member_id  →  PresenceRecord
    Records expire after settings.presence_ttl_secs (default 300s).
    """

    def __init__(self, ttl_secs: int | None = None):
        self._ttl = ttl_secs or settings.presence_ttl_secs
        # { "hh_id:member_id": PresenceRecord }
        self._store: dict[str, PresenceRecord] = {}

    # ── Writes ───────────────────────────────────────────────

    def update(
        self,
        household_id: str,
        member_id: str,
        room_id: Optional[str] = None,
        is_home: bool = True,
    ) -> None:
        key = f"{household_id}:{member_id}"
        self._store[key] = PresenceRecord(
            member_id=member_id,
            room_id=room_id,
            is_home=is_home,
        )
        logger.debug(f"Presence updated: {key} room={room_id} home={is_home}")

    def mark_left(self, household_id: str, member_id: str) -> None:
        """Explicitly mark a member as having left the household."""
        key = f"{household_id}:{member_id}"
        if key in self._store:
            r = self._store[key]
            r.is_home = False
            r.room_id = None
            r.updated_at = time.monotonic()

    # ── Reads ────────────────────────────────────────────────

    def _is_expired(self, record: PresenceRecord) -> bool:
        return (time.monotonic() - record.updated_at) > self._ttl

    def get_all(self, household_id: str) -> list[PresenceRecord]:
        """Return all non-expired presence records for the household."""
        prefix = f"{household_id}:"
        return [
            r for key, r in self._store.items()
            if key.startswith(prefix) and not self._is_expired(r)
        ]

    def get_member_room(self, household_id: str, member_id: str) -> Optional[str]:
        key = f"{household_id}:{member_id}"
        r = self._store.get(key)
        if r and not self._is_expired(r):
            return r.room_id
        return None

    def is_home(self, household_id: str, member_id: str) -> bool:
        key = f"{household_id}:{member_id}"
        r = self._store.get(key)
        if r and not self._is_expired(r):
            return r.is_home
        return False

    def get_home_member_ids(self, household_id: str) -> list[str]:
        return [r.member_id for r in self.get_all(household_id) if r.is_home]

    # ── Housekeeping ─────────────────────────────────────────

    def evict_expired(self) -> int:
        """Remove all expired records. Returns count removed."""
        stale = [k for k, r in self._store.items() if self._is_expired(r)]
        for k in stale:
            del self._store[k]
        return len(stale)
