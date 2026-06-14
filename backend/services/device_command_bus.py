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

# Fields written to household_graph when state changes
_STATE_FIELDS = frozenset({
    "state", "mode", "temperature_set_c", "temperature_c",
    "volume_percent", "door_open_seconds", "brightness_pct",
})


async def persist_device_state(
    household_id: str,
    device_id: str,
    state: dict,
) -> None:
    """Merge device state fields onto the graph node in DynamoDB."""
    updates = {k: v for k, v in state.items() if k in _STATE_FIELDS and v is not None}
    if not updates:
        return
    try:
        from db.dynamo_client import async_execute
        from graph_repository import GraphRepository

        table = get_table("household_graph")
        update_expr = "SET "
        expr_vals: dict = {}
        expr_names: dict = {}
        for k, v in updates.items():
            update_expr += f"#{k} = :{k}, "
            expr_vals[f":{k}"] = Decimal(str(v)) if isinstance(v, float) else v
            expr_names[f"#{k}"] = k
        update_expr = update_expr.rstrip(", ")
        await async_execute(
            table.update_item,
            Key={
                "PK": f"HOUSEHOLD#{household_id}",
                "SK": f"NODE#{device_id}",
            },
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_vals,
            ExpressionAttributeNames=expr_names,
        )
        GraphRepository().invalidate_cache(household_id)
    except Exception as e:
        logger.error(f"Failed to persist device state for {device_id}: {e}")


class DeviceCommandBus:
    """
    Dispatches device commands with idempotency, state capture, and audit logging.
    """

    def __init__(self):
        # { "device_id:command": last_dispatch_timestamp }
        self._idem_cache: dict[str, float] = {}

    async def dispatch(self, action: Action) -> CommandResult:
        """
        Dispatch a DEVICE_COMMAND action. Returns CommandResult.
        """
        start = time.monotonic()
        device_id = action.device_id or "unknown"
        command = action.command or "unknown"

        # Step 1: Idempotency check
        idem_key_local = f"{device_id}:{command}"
        idem_key_redis = f"saathi:v1:idem:cmd:{device_id}:{command}"
        
        # Try Redis first
        from db.redis_client import redis_client
        lock_acquired = await redis_client.acquire_idempotency_lock(idem_key_redis, _IDEM_WINDOW_SECS)
        
        if lock_acquired is False:
            # Redis denied the lock -> duplicate command
            logger.info(f"CommandBus: duplicate suppressed by Redis {idem_key_redis}")
            return CommandResult(
                action_id=action.action_id,
                device_id=device_id,
                command=command,
                success=False,
                error="Idempotency suppressed — same command dispatched within 60s",
                latency_ms=(time.monotonic() - start) * 1000,
                idempotency_key=idem_key_redis,
            )
        elif lock_acquired is None:
            # Redis failed -> fallback to local memory check
            last = self._idem_cache.get(idem_key_local, 0)
            if (time.monotonic() - last) < _IDEM_WINDOW_SECS:
                logger.info(f"CommandBus: duplicate suppressed by local fallback {idem_key_local}")
                return CommandResult(
                    action_id=action.action_id,
                    device_id=device_id,
                    command=command,
                    success=False,
                    error="Idempotency suppressed — same command dispatched within 60s",
                    latency_ms=(time.monotonic() - start) * 1000,
                    idempotency_key=idem_key_local,
                )
            # Local lock acquired
            self._idem_cache[idem_key_local] = time.monotonic()

        # Step 2: Capture pre-state (mock)
        pre_state = await self._get_device_state(device_id, action.household_id)

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

        # Step 4: Mark idempotency (update local fallback cache unconditionally)
        self._idem_cache[idem_key_local] = time.monotonic()

        latency_ms = (time.monotonic() - start) * 1000

        # Step 4.5 Update device state in DynamoDB graph so the frontend devices page updates
        if success and post_state and device_id != "unknown":
            try:
                await persist_device_state(action.household_id, device_id, post_state)
            except Exception as e:
                logger.error(f"Failed to update device state in graph: {e}")

        result = CommandResult(
            action_id=action.action_id,
            device_id=device_id,
            command=command,
            success=success,
            pre_state=pre_state,
            post_state=post_state,
            error=error,
            latency_ms=latency_ms,
            idempotency_key=idem_key_redis,
        )

        # Step 5: Write to ActionLog (non-blocking)
        await self._write_action_log(action, result)

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
            "set_volume_max_20": {"volume_percent": 20, "state": "on"},
            "set_volume_20":     {"volume_percent": 20, "state": "on"},
            "set_warm_white":    {"mode": "warm_white", "state": "on"},
            "set_volume_max_40": {"volume_percent": 40, "state": "on"},
            "set_volume_max_50": {"volume_percent": 50, "state": "on"},
            "set_temp_22":       {"state": "on", "temperature_set_c": 22, "mode": "cool"},
            "set_temp_24":       {"state": "on", "temperature_set_c": 24, "mode": "cool"},
        }
        post_state = _CMD_STATES.get(command, {"command_applied": command})
        return True, post_state, None

    async def _get_device_state(self, device_id: str, household_id: str) -> dict:
        """Return last known device state from DynamoDB (best-effort)."""
        try:
            from db.dynamo_client import async_execute
            table = get_table("household_graph")
            resp = await async_execute(
                table.get_item,
                Key={
                    "PK": f"HOUSEHOLD#{household_id}",
                    "SK": f"NODE#{device_id}",
                },
            )
            item = resp.get("Item")
            if item:
                return {
                    k: item[k]
                    for k in ("state", "device_type", "room", "mode", "temperature_set_c", "volume_percent")
                    if item.get(k) is not None
                }
        except Exception:
            pass
        return {}

    async def _write_action_log(self, action: Action, result: CommandResult) -> None:
        """Write dispatch record to ActionLog with 30-day TTL."""
        try:
            import asyncio
            from decimal import Decimal
            from db.dynamo_client import async_execute
            table = get_table("action_log")
            ttl = int(time.time()) + (settings.ACTION_LOG_TTL_DAYS * 86400)
            now_iso = datetime.now(tz=timezone.utc).isoformat()
            item = {
                "action_id":    action.action_id,
                "created_at":   now_iso,          # GSI range key (normalised)
                "household_id": action.household_id,
                "timestamp":    now_iso,          # keep for backward compat
                "action_type":  action.action_type.value,
                "source":       action.source.value,
                "command":      action.command or "",
                "success":      result.success,
                "latency_ms":   Decimal(str(round(result.latency_ms, 2))),
                "rule_id":      action.rule_id or "",
                "audit_expiry": ttl,
            }
            # Only include device_id when it's a real non-empty value.
            # An empty string causes the UI to render a blank device name.
            if action.device_id:
                item["device_id"] = action.device_id
            if result.error:
                item["error"] = result.error
            await async_execute(table.put_item, Item=item)
        except Exception as e:
            logger.debug(f"ActionLog write failed (non-critical): {e}")
