"""
notification_service.py — Phase 10.3 / 10.4
=============================================
NotificationService.notify(notification) → bool
notify_bedrock_degradation(household_id) → None

Pipeline:
  1. Rate limit check  — max 3 notifications/member/10min
  2. Channel resolve   — from graph (voice / mobile / both)
  3. Language resolve  — from member node (hindi / english)
  4. Format message    — channel-specific formatting
  5. Simulate dispatch — log to ActionLog, return success
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from config import settings
from db.dynamo_client import get_table
from schemas.actions import Action, Notification
from schemas.enums import ActionSource, ActionType, NotificationChannel

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Handles all notifications (voice, mobile, both).
    Rate-limited: max NOTIFICATION_RATE_LIMIT_COUNT per member per window.
    """

    def __init__(self):
        # Rate tracker: member_id → [timestamp, ...]
        self._rate_tracker: dict[str, list[float]] = defaultdict(list)
        self._window_secs = settings.NOTIFICATION_RATE_LIMIT_WINDOW_SECS   # 600s
        self._max_per_window = settings.NOTIFICATION_RATE_LIMIT_COUNT       # 3

    # ── 10.3 Main notify ─────────────────────────────────────

    async def notify(self, notification: Notification) -> bool:
        """
        Send a notification to target members.
        Returns True if dispatched, False if rate-limited.
        Uses distributed Redis Sliding Window if available, falls back to memory.
        """
        now = time.monotonic()
        cutoff = now - self._window_secs

        from db.redis_client import redis_client

        for member_id in notification.target_member_ids:
            redis_key = f"saathi:v1:rate:notify:{member_id}"
            redis_allowed = await redis_client.check_rate_limit(
                redis_key, self._max_per_window, self._window_secs
            )

            if redis_allowed is False:
                logger.warning(f"NotificationService: rate-limited member={member_id} (Redis)")
                notification.rate_limited = True
                return False
            elif redis_allowed is None:
                # Fallback to local memory
                self._rate_tracker[member_id] = [
                    t for t in self._rate_tracker[member_id] if t > cutoff
                ]
                if len(self._rate_tracker[member_id]) >= self._max_per_window:
                    logger.warning(
                        f"NotificationService: rate-limited member={member_id} "
                        f"({len(self._rate_tracker[member_id])}/{self._max_per_window}) (Fallback)"
                    )
                    notification.rate_limited = True
                    return False
                self._rate_tracker[member_id].append(now)

        # Note: If Redis is ON, `check_rate_limit` already added the timestamp atomically!
        # We don't need to append to `self._rate_tracker` on success if Redis is active,
        # but the fallback block above handles local tracking when Redis is OFF.

        # Simulate dispatch
        formatted = self._format_message(notification)
        self._simulate_dispatch(notification, formatted)
        await self._write_notification_log(notification, formatted)

        notification.sent = True
        notification.sent_at = datetime.now(tz=timezone.utc)
        logger.info(
            f"NotificationService: sent to {notification.target_member_ids} "
            f"channel={notification.channel.value if notification.channel else 'any'} "
            f"lang={notification.language}"
        )
        return True

    # ── 10.4 Bedrock degradation ──────────────────────────────

    async def notify_bedrock_degradation(self, household_id: str) -> None:
        """
        Fires when Bedrock circuit breaker opens.
        Targets primary coordinator (mbr_papa_003 by convention for Sharma family).
        Message always in English — degradation is a technical alert.
        """
        notif = Notification(
            household_id=household_id,
            target_member_ids=["mbr_papa_003"],
            channel=NotificationChannel.MOBILE_PUSH,
            language="english",
            message=(
                "SAATHI Alert: AI reasoning temporarily unavailable. "
                "Rule-based automation is still active (85% functionality). "
                "Normal service will resume automatically."
            ),
            title="SAATHI — AI Temporarily Unavailable",
            source=ActionSource.RULE_ENGINE,
        )
        await self.notify(notif)
        logger.warning(
            f"NotificationService: Bedrock degradation alert sent for {household_id}"
        )

    # ── Helpers ──────────────────────────────────────────────

    def _format_message(self, notification: Notification) -> str:
        """
        Format message for channel. Voice messages are shorter; mobile gets full text.
        """
        if notification.channel == NotificationChannel.ALEXA_VOICE:
            # Truncate for voice (< 200 chars ideally)
            return notification.message[:200]
        return notification.message

    def _simulate_dispatch(self, notification: Notification, formatted: str) -> None:
        """
        Dispatch notification via Twilio (WhatsApp / SMS) when TWILIO_ENABLED=true.
        Falls back to structured log for:
          - ALEXA_VOICE / MOBILE_PUSH / VOICE_AND_MOBILE  (separate integrations)
          - Any channel when Twilio is disabled or a phone number is missing
        """
        if settings.twilio_enabled:
            self._twilio_dispatch(notification, formatted)
        else:
            channel = notification.channel.value if notification.channel else "mobile"
            for member_id in notification.target_member_ids:
                logger.debug(
                    f"  [SIM] {channel.upper()} -> {member_id}: {formatted[:80]}..."
                )

    def _twilio_dispatch(self, notification: Notification, formatted: str) -> None:
        """Send real messages via Twilio. Called only when TWILIO_ENABLED=true."""
        try:
            from twilio.rest import Client
            from twilio.base.exceptions import TwilioRestException
        except ImportError:
            logger.error("Twilio package not installed — run: pip install twilio==9.3.5")
            return

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        phone_map = settings.member_phone_map
        channel = notification.channel

        for member_id in notification.target_member_ids:
            to_phone = phone_map.get(member_id)
            if not to_phone:
                logger.warning(
                    f"NotificationService: no phone number for member={member_id} "
                    f"— add to MEMBER_PHONE_MAP in .env"
                )
                continue

            try:
                if channel in (
                    NotificationChannel.WHATSAPP,
                    NotificationChannel.VOICE_AND_MOBILE,
                ):
                    msg = client.messages.create(
                        from_=settings.twilio_from_whatsapp,
                        to=f"whatsapp:{to_phone}",
                        body=formatted,
                    )
                    logger.info(
                        f"NotificationService: WhatsApp sent to {member_id} "
                        f"({to_phone}) sid={msg.sid}"
                    )

                if channel in (
                    NotificationChannel.SMS,
                    NotificationChannel.MOBILE_PUSH,  # fallback until FCM is wired
                ):
                    if not settings.twilio_from_sms:
                        logger.warning(
                            "NotificationService: TWILIO_FROM_SMS not set — "
                            f"skipping SMS for {member_id}"
                        )
                        continue
                    msg = client.messages.create(
                        from_=settings.twilio_from_sms,
                        to=to_phone,
                        body=formatted,
                    )
                    logger.info(
                        f"NotificationService: SMS sent to {member_id} "
                        f"({to_phone}) sid={msg.sid}"
                    )

                if channel == NotificationChannel.ALEXA_VOICE:
                    # Alexa TTS is a separate Alexa Skills Kit integration
                    logger.debug(
                        f"  [VOICE] Alexa TTS not wired yet -> {member_id}: {formatted[:80]}..."
                    )

            except TwilioRestException as e:
                logger.error(
                    f"NotificationService: Twilio error for {member_id} "
                    f"code={e.code} msg={e.msg}"
                )
                notification.error = f"twilio_error:{e.code}"

    async def _write_notification_log(self, notification: Notification, formatted: str) -> None:
        """Write notification record to ActionLog."""
        try:
            import time as _t
            table = get_table("action_log")
            ttl = int(_t.time()) + (settings.ACTION_LOG_TTL_DAYS * 86400)
            item = {
                "action_id":     notification.notification_id,
                "household_id":  notification.household_id,
                "timestamp":     datetime.now(tz=timezone.utc).isoformat(),
                "action_type":   "notification",
                "source":        notification.source.value,
                "target_members": notification.target_member_ids,
                "channel":       notification.channel.value if notification.channel else "mobile_push",
                "language":      notification.language,
                "message":       formatted[:500],
                "sent":          notification.sent,
                "rate_limited":  notification.rate_limited,
                "audit_expiry":  ttl,
            }
            from db.dynamo_client import async_execute
            await async_execute(table.put_item, Item=item)
        except Exception as e:
            logger.debug(f"Notification log write failed (non-critical): {e}")

    def from_action(self, action: Action) -> Notification:
        """Convert a NOTIFICATION Action into a Notification object."""
        return Notification(
            household_id=action.household_id,
            target_member_ids=action.target_member_ids or [],
            channel=action.channel or NotificationChannel.MOBILE_PUSH,
            language=action.language or "hindi",
            message=action.message or "",
            source=action.source,
            action_id=action.action_id,
            event_id=action.event_id,
            device_id=action.device_id,
        )
