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

    # ── Redis Integration ────────────────────────────────────

    def _fire_and_forget(self, coro_factory, *args):
        from services.task_tracker import task_tracker
        task_tracker.spawn(coro_factory, *args, fallback="drop")

    async def _push_to_redis(self, household_id: str, member_id: str, room_id: Optional[str], is_home: bool) -> None:
        """Write presence state to Redis with native TTL and broadcast via Pub/Sub."""
        try:
            import json
            from db.redis_client import redis_client
            if not redis_client._redis:
                return
            
            key = f"saathi:v1:presence:{household_id}:{member_id}"
            payload = json.dumps({
                "household_id": household_id,
                "member_id": member_id,
                "room_id": room_id,
                "is_home": is_home,
            })
            # Pipeline for atomicity and efficiency
            async with redis_client._redis.pipeline() as pipe:
                pipe.set(key, payload, ex=self._ttl)
                pipe.publish("saathi:v1:presence_events", payload)
                await pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to push presence to Redis for {member_id}: {e}")

    async def start_subscriber(self) -> None:
        """Listen for Pub/Sub updates from other pods."""
        import json
        from db.redis_client import redis_client
        
        while True:
            try:
                if not redis_client._redis:
                    import asyncio
                    await asyncio.sleep(5)
                    continue

                pubsub = redis_client._redis.pubsub()
                await pubsub.subscribe("saathi:v1:presence_events")
                logger.info("PresenceService: Subscribed to saathi:v1:presence_events")

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            hh_id = data["household_id"]
                            mem_id = data["member_id"]
                            key = f"{hh_id}:{mem_id}"
                            
                            # Update local memory
                            self._store[key] = PresenceRecord(
                                member_id=mem_id,
                                room_id=data.get("room_id"),
                                is_home=data.get("is_home", True),
                            )
                            # Update timestamp manually just in case so TTL logic works locally too
                            self._store[key].updated_at = time.monotonic()
                        except Exception as e:
                            logger.error(f"PresenceService Pub/Sub parse error: {e}")
            except Exception as e:
                logger.warning(f"PresenceService Pub/Sub connection lost: {e}. Retrying in 5s...")
                import asyncio
                await asyncio.sleep(5)

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
        self._fire_and_forget(self._push_to_redis, household_id, member_id, room_id, is_home)

    def mark_left(self, household_id: str, member_id: str) -> None:
        """Explicitly mark a member as having left the household."""
        key = f"{household_id}:{member_id}"
        if key in self._store:
            r = self._store[key]
            r.is_home = False
            r.room_id = None
            r.updated_at = time.monotonic()
            self._fire_and_forget(self._push_to_redis, household_id, member_id, None, False)

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
