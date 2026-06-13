"""
action_planner.py — Phase 10.1
================================
ActionPlanner processes proposed actions through a 4-step pipeline:
  1. Consent check   — CRITICAL / SAFETY actions auto-approve; others need consent
  2. Conflict resolve — deduplicate contradictory commands on the same device
  3. Rate limit       — cap device commands at 5/hour per device
  4. Schedule         — pass-through (scheduling is advisory only at this layer)

Each step emits a WebSocket `action_planner_step` event via the ConnectionManager
injected at construction time (optional — graceful no-op if not provided).
"""

import logging
import time
from collections import defaultdict
from typing import Any, Callable

from schemas.actions import Action
from schemas.enums import ActionSource, ActionType, ConsentLevel, ImpactLevel
from schemas.intelligence import HouseholdContext

logger = logging.getLogger(__name__)

# Max device commands per device per hour
_RATE_LIMIT_DEVICE_COMMANDS_PER_HOUR = 5
_RATE_LIMIT_WINDOW_SECS = 3600


class ActionPlanner:
    """
    Processes proposed actions through the 4-step planning pipeline.
    Returns only approved actions; rejected actions are logged.

    Inject a `broadcast_fn` (async callable) to emit WebSocket step events.
    """

    def __init__(self, broadcast_fn: Callable | None = None):
        self._broadcast = broadcast_fn
        # Rate-limit tracker: device_id → list of command timestamps
        self._rate_tracker: dict[str, list[float]] = defaultdict(list)

    def plan(
        self,
        proposed: list[Action],
        context: HouseholdContext | None = None,
    ) -> list[Action]:
        """
        Run the 4-step pipeline. Returns the list of approved Actions.
        """
        approved = list(proposed)

        # Step 1: Consent check
        approved, rejected_consent = self._consent_check(approved)
        self._emit_step("consent_check", len(approved), rejected_consent)

        # Step 2: Conflict resolve
        approved, resolved = self._conflict_resolve(approved)
        self._emit_step("conflict_resolve", len(approved), resolved)

        # Step 3: Rate limit
        approved, rate_limited = self._rate_limit(approved)
        self._emit_step("rate_limit", len(approved), rate_limited)

        # Step 4: Schedule (pass-through — schedule field is advisory)
        self._emit_step("schedule", len(approved), [])

        logger.info(
            f"ActionPlanner: proposed={len(proposed)} approved={len(approved)} "
            f"consent_rejected={len(rejected_consent)} "
            f"rate_limited={len(rate_limited)}"
        )
        return approved

    # ── Step 1: Consent ──────────────────────────────────────

    def _consent_check(
        self, actions: list[Action]
    ) -> tuple[list[Action], list[Action]]:
        """
        SAFETY + CRITICAL auto-approve.
        DEVICE_COMMANDs from BEDROCK need consent = CONFIRM.
        Notifications always pass through.
        """
        approved, rejected = [], []
        for a in actions:
            # Notifications and safety always pass
            if a.action_type == ActionType.NOTIFICATION:
                approved.append(a)
                continue
            if a.source == ActionSource.RULE_ENGINE:
                # Rule engine actions are pre-approved by definition
                approved.append(a)
                continue
            # Bedrock device commands — AUTO_NOTIFY and above are auto-approved
            if a.consent_level in (
                ConsentLevel.SUGGEST,
                ConsentLevel.AUTO_NOTIFY,
                ConsentLevel.FULL_AUTO,
            ):
                approved.append(a)
            else:
                # OBSERVE level — log only, no dispatch
                rejected.append(a)
        return approved, rejected

    # ── Step 2: Conflict resolve ──────────────────────────────

    def _conflict_resolve(
        self, actions: list[Action]
    ) -> tuple[list[Action], list[Action]]:
        """
        If multiple DEVICE_COMMAND actions target the same device_id,
        keep only the highest-priority one (RULE_ENGINE > BEDROCK).
        """
        seen_devices: dict[str, Action] = {}
        conflicts = []

        for a in actions:
            if a.action_type != ActionType.DEVICE_COMMAND or not a.device_id:
                continue
            existing = seen_devices.get(a.device_id)
            if existing:
                # Prefer RULE_ENGINE over BEDROCK
                if a.source == ActionSource.RULE_ENGINE:
                    conflicts.append(existing)
                    seen_devices[a.device_id] = a
                else:
                    conflicts.append(a)
            else:
                seen_devices[a.device_id] = a

        # Build approved: non-device actions + winning device actions
        approved = [
            a for a in actions
            if a.action_type != ActionType.DEVICE_COMMAND or a.device_id not in seen_devices
        ] + list(seen_devices.values())

        return approved, conflicts

    # ── Step 3: Rate limit ────────────────────────────────────

    def _rate_limit(
        self, actions: list[Action]
    ) -> tuple[list[Action], list[Action]]:
        """
        Block device commands if the same device has had >= 5 commands in the last hour.
        """
        approved, limited = [], []
        now = time.monotonic()
        cutoff = now - _RATE_LIMIT_WINDOW_SECS

        for a in actions:
            if a.action_type != ActionType.DEVICE_COMMAND or not a.device_id:
                approved.append(a)
                continue

            # Evict old timestamps
            self._rate_tracker[a.device_id] = [
                t for t in self._rate_tracker[a.device_id] if t > cutoff
            ]

            if len(self._rate_tracker[a.device_id]) >= _RATE_LIMIT_DEVICE_COMMANDS_PER_HOUR:
                logger.warning(f"ActionPlanner: rate-limited action for device {a.device_id}")
                limited.append(a)
            else:
                self._rate_tracker[a.device_id].append(now)
                approved.append(a)

        return approved, limited

    # ── WebSocket emission ────────────────────────────────────

    def _emit_step(self, step: str, approved_count: int, rejected: list[Action]) -> None:
        if not self._broadcast:
            return
        import asyncio
        data = {
            "step": step,
            "approved_count": approved_count,
            "rejected_count": len(rejected),
            "rejected_ids": [a.action_id for a in rejected],
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast("action_planner_step", data))
        except RuntimeError:
            pass
