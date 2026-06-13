"""
device_command_bus.py — Phase 10.2
====================================
DeviceCommandBus.dispatch(action) → CommandResult

Pipeline:
  1. Idempotency check  — block duplicate commands on same device within 60s
  2. Simulated dispatch — mimics Alexa/smart-home API call (or real API)
  3. Capture pre/post state — reads device state before + after
  4. Write to ActionLog DynamoDB with TTL 30 days
  5. Return CommandResult

DEVICE_MOCK_MODE (always True for demo) returns success immediately.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from config import settings
from db.dynamo_client import get_table
from schemas.actions import Action, CommandResult

logger = logging.getLogger(__name__)

# Idempotency window: same device + command within 60s → block
_IDEM_WINDOW_SECS = 60


class DeviceCommandBus:
    """
    Dispatches device commands with idempotency, state capture, and audit logging.
    """

    def __init__(self):
        # { "device_id:command": last_dispatch_timestamp }
        self._idem_cache: dict[str, float] = {}

    def dispatch(self, action: Action) -> CommandResult:
        """
        Dispatch a DEVICE_COMMAND action. Returns CommandResult.
        """
        start = time.monotonic()
        device_id = action.device_id or "unknown"
        command = action.command or "unknown"

        # Step 1: Idempotency check
        idem_key = f"{device_id}:{command}"
        last = self._idem_cache.get(idem_key, 0)
        if (time.monotonic() - last) < _IDEM_WINDOW_SECS:
            logger.info(f"CommandBus: duplicate suppressed {idem_key}")
            return CommandResult(
                action_id=action.action_id,
                device_id=device_id,
                command=command,
                success=False,
                error="Idempotency suppressed — same command dispatched within 60s",
                latency_ms=(time.monotonic() - start) * 1000,
                idempotency_key=idem_key,
            )

        # Step 2: Capture pre-state (mock)
        pre_state = self._get_device_state(device_id)

        # Step 3: Dispatch (simulated)
        try:
            success, post_state, error = self._simulate_dispatch(device_id, command)
        except Exception as e:
            logger.error(f"CommandBus: dispatch error {e}")
            return CommandResult(
                action_id=action.action_id,
                device_id=device_id,
                command=command,
                success=False,
                pre_state=pre_state,
                error=str(e),
                latency_ms=(time.monotonic() - start) * 1000,
            )

        # Step 4: Mark idempotency
        self._idem_cache[idem_key] = time.monotonic()

        latency_ms = (time.monotonic() - start) * 1000

        result = CommandResult(
            action_id=action.action_id,
            device_id=device_id,
            command=command,
            success=success,
            pre_state=pre_state,
            post_state=post_state,
            error=error,
            latency_ms=latency_ms,
            idempotency_key=idem_key,
        )

        # Step 5: Write to ActionLog (non-blocking)
        self._write_action_log(action, result)

        logger.info(
            f"CommandBus: dispatched device={device_id} cmd={command} "
            f"success={success} latency={latency_ms:.1f}ms"
        )
        return result

    # ── Simulation layer ──────────────────────────────────────

    def _simulate_dispatch(
        self, device_id: str, command: str
    ) -> tuple[bool, dict, str | None]:
        """
        Simulate smart-home API response.
        In production, replace with real Alexa/Google Home API call.
        """
        # Map commands to simulated post-states
        _CMD_STATES = {
            "turn_off":          {"state": "off"},
            "turn_on":           {"state": "on"},
            "set_volume_max_20": {"volume_percent": 20},
            "set_warm_white":    {"mode": "warm_white", "state": "on"},
            "set_volume_max_40": {"volume_percent": 40},
            "set_volume_max_50": {"volume_percent": 50},
        }
        post_state = _CMD_STATES.get(command, {"command_applied": command})
        return True, post_state, None

    def _get_device_state(self, device_id: str) -> dict:
        """Return last known device state from DynamoDB (best-effort)."""
        try:
            table = get_table("household_graph")
            from boto3.dynamodb.conditions import Key, Attr
            resp = table.query(
                KeyConditionExpression=Key("household_id").eq(settings.household_id),
                FilterExpression=Attr("node_id").eq(device_id),
                Limit=1,
            )
            items = resp.get("Items", [])
            if items:
                return {k: items[0].get(k) for k in ("state", "device_type", "room_id") if items[0].get(k)}
        except Exception:
            pass
        return {}

    def _write_action_log(self, action: Action, result: CommandResult) -> None:
        """Write dispatch record to ActionLog with 30-day TTL."""
        try:
            import asyncio
            from decimal import Decimal
            table = get_table("action_log")
            ttl = int(time.time()) + (settings.ACTION_LOG_TTL_DAYS * 86400)
            item = {
                "action_id":   action.action_id,
                "household_id": action.household_id,
                "timestamp":   datetime.now(tz=timezone.utc).isoformat(),
                "action_type": action.action_type.value,
                "source":      action.source.value,
                "device_id":   action.device_id or "",
                "command":     action.command or "",
                "success":     result.success,
                "latency_ms":  Decimal(str(round(result.latency_ms, 2))),
                "rule_id":     action.rule_id or "",
                "audit_expiry": ttl,
            }
            if result.error:
                item["error"] = result.error
            table.put_item(Item=item)
        except Exception as e:
            logger.debug(f"ActionLog write failed (non-critical): {e}")
