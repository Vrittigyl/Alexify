"""
test_twilio_notification.py
============================
Unit tests for Twilio dispatch in NotificationService._twilio_dispatch().

All tests mock twilio.rest.Client — no real network calls are made.
The suite covers:
  - WhatsApp channel sends to whatsapp:<phone>
  - SMS / MOBILE_PUSH channel sends to bare E.164 number
  - VOICE_AND_MOBILE sends WhatsApp (and SMS when from_sms is set)
  - ALEXA_VOICE is skipped (Twilio has no voice hook yet)
  - Missing phone number in MEMBER_PHONE_MAP → warning, no send
  - Missing TWILIO_FROM_SMS → warning, skip SMS only
  - TwilioRestException → error logged, notification.error set, pipeline continues
  - TWILIO_ENABLED=False → simulate-log path, no Twilio client instantiated
  - Full notify() integration: TWILIO_ENABLED=True, rate-limit pass → real dispatch
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from schemas.actions import Notification
from schemas.enums import ActionSource, NotificationChannel
from services.notification_service import NotificationService

HH_ID = "hh_xk92p_sharma"
MEMBER_ID = "mbr_papa_003"
PHONE = "+917989975430"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_notification(
    channel: NotificationChannel = NotificationChannel.WHATSAPP,
    member_id: str = MEMBER_ID,
    message: str = "🏠 SAATHI test",
) -> Notification:
    return Notification(
        household_id=HH_ID,
        target_member_ids=[member_id],
        channel=channel,
        source=ActionSource.RULE_ENGINE,
        language="english",
        message=message,
    )


@pytest.fixture
def twilio_settings():
    """Patch settings so Twilio is enabled with known test credentials."""
    with patch("services.notification_service.settings") as mock_settings:
        mock_settings.twilio_enabled = True
        mock_settings.twilio_account_sid = "ACtest000000000000000000000000000"
        mock_settings.twilio_auth_token = "test_auth_token_000000000000000000"
        mock_settings.twilio_from_whatsapp = "whatsapp:+14155238886"
        mock_settings.twilio_from_sms = "+14155551234"
        mock_settings.member_phone_map = {MEMBER_ID: PHONE}
        mock_settings.NOTIFICATION_RATE_LIMIT_WINDOW_SECS = 600
        mock_settings.NOTIFICATION_RATE_LIMIT_COUNT = 3
        mock_settings.ACTION_LOG_TTL_DAYS = 30
        yield mock_settings


@pytest.fixture
def mock_twilio_client():
    """Patch twilio.rest.Client with a MagicMock."""
    mock_msg = MagicMock()
    mock_msg.sid = "SMtest000000000000000000000000000"
    mock_msg.status = "queued"

    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = mock_msg

    with patch(
        "services.notification_service.NotificationService._twilio_dispatch",
        wraps=None,  # will be replaced per-test
    ):
        pass  # just ensuring the patch target is importable

    with patch("twilio.rest.Client", return_value=mock_client_instance) as MockClient:
        yield MockClient, mock_client_instance


@pytest.fixture(autouse=True)
def mock_dynamo_log():
    """Suppress DynamoDB writes in all tests."""
    with patch(
        "services.notification_service.NotificationService._write_notification_log",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture(autouse=True)
def mock_redis_disabled():
    """Keep Redis off so rate-limit uses in-memory fallback."""
    async def _allow(*args, **kwargs):
        return None  # None → use local memory tracker

    with patch("db.redis_client.redis_client.check_rate_limit", side_effect=_allow):
        yield


# ── WhatsApp dispatch ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_whatsapp_sends_to_correct_number(twilio_settings, mock_twilio_client):
    MockClient, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.WHATSAPP)

    svc._twilio_dispatch(notif, notif.message)

    client_instance.messages.create.assert_called_once_with(
        from_="whatsapp:+14155238886",
        to=f"whatsapp:{PHONE}",
        body=notif.message,
    )


@pytest.mark.asyncio
async def test_whatsapp_logs_sid_on_success(twilio_settings, mock_twilio_client, caplog):
    import logging
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.WHATSAPP)

    with caplog.at_level(logging.INFO):
        svc._twilio_dispatch(notif, notif.message)

    assert "SMtest" in caplog.text
    assert MEMBER_ID in caplog.text


# ── SMS / MOBILE_PUSH dispatch ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sms_sends_to_bare_phone(twilio_settings, mock_twilio_client):
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.SMS)

    svc._twilio_dispatch(notif, notif.message)

    client_instance.messages.create.assert_called_once_with(
        from_="+14155551234",
        to=PHONE,
        body=notif.message,
    )


@pytest.mark.asyncio
async def test_mobile_push_falls_back_to_sms(twilio_settings, mock_twilio_client):
    """MOBILE_PUSH is dispatched as SMS until FCM is wired."""
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.MOBILE_PUSH)

    svc._twilio_dispatch(notif, notif.message)

    client_instance.messages.create.assert_called_once_with(
        from_="+14155551234",
        to=PHONE,
        body=notif.message,
    )


# ── VOICE_AND_MOBILE ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_voice_and_mobile_sends_whatsapp_and_sms(twilio_settings, mock_twilio_client):
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.VOICE_AND_MOBILE)

    svc._twilio_dispatch(notif, notif.message)

    calls = client_instance.messages.create.call_args_list
    assert len(calls) == 2

    # WhatsApp call
    assert calls[0] == call(
        from_="whatsapp:+14155238886",
        to=f"whatsapp:{PHONE}",
        body=notif.message,
    )
    # SMS call
    assert calls[1] == call(
        from_="+14155551234",
        to=PHONE,
        body=notif.message,
    )


# ── ALEXA_VOICE ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alexa_voice_does_not_call_twilio(twilio_settings, mock_twilio_client):
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.ALEXA_VOICE)

    svc._twilio_dispatch(notif, notif.message[:200])

    client_instance.messages.create.assert_not_called()


# ── Missing phone number ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_phone_number_warns_and_skips(twilio_settings, mock_twilio_client, caplog):
    import logging
    twilio_settings.member_phone_map = {}  # no phone for anyone
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.WHATSAPP)

    with caplog.at_level(logging.WARNING):
        svc._twilio_dispatch(notif, notif.message)

    client_instance.messages.create.assert_not_called()
    assert "no phone number" in caplog.text
    assert MEMBER_ID in caplog.text


# ── Missing TWILIO_FROM_SMS ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_from_sms_warns_and_skips_sms(twilio_settings, mock_twilio_client, caplog):
    import logging
    twilio_settings.twilio_from_sms = ""  # not configured
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.SMS)

    with caplog.at_level(logging.WARNING):
        svc._twilio_dispatch(notif, notif.message)

    client_instance.messages.create.assert_not_called()
    assert "TWILIO_FROM_SMS not set" in caplog.text


# ── TwilioRestException ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_twilio_rest_exception_sets_error_on_notification(twilio_settings, mock_twilio_client):
    from twilio.base.exceptions import TwilioRestException
    _, client_instance = mock_twilio_client

    client_instance.messages.create.side_effect = TwilioRestException(
        status=400, uri="/Messages.json", msg="The number is unverified", code=21608
    )

    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.WHATSAPP)

    # Should not raise
    svc._twilio_dispatch(notif, notif.message)

    assert notif.error is not None
    assert "21608" in notif.error


@pytest.mark.asyncio
async def test_twilio_rest_exception_logs_error(twilio_settings, mock_twilio_client, caplog):
    import logging
    from twilio.base.exceptions import TwilioRestException
    _, client_instance = mock_twilio_client

    client_instance.messages.create.side_effect = TwilioRestException(
        status=401, uri="/Messages.json", msg="Authentication Error", code=20003
    )

    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.WHATSAPP)

    with caplog.at_level(logging.ERROR):
        svc._twilio_dispatch(notif, notif.message)

    assert "20003" in caplog.text


# ── TWILIO_ENABLED=False → simulate path ─────────────────────────────────────

@pytest.mark.asyncio
async def test_twilio_disabled_uses_log_path(caplog):
    import logging
    with patch("services.notification_service.settings") as mock_settings:
        mock_settings.twilio_enabled = False
        mock_settings.NOTIFICATION_RATE_LIMIT_WINDOW_SECS = 600
        mock_settings.NOTIFICATION_RATE_LIMIT_COUNT = 3
        mock_settings.ACTION_LOG_TTL_DAYS = 30

        svc = NotificationService()
        notif = make_notification(channel=NotificationChannel.WHATSAPP)

        with patch(
            "services.notification_service.NotificationService._twilio_dispatch"
        ) as mock_dispatch:
            with caplog.at_level(logging.DEBUG):
                svc._simulate_dispatch(notif, notif.message)

            mock_dispatch.assert_not_called()

    assert "WHATSAPP" in caplog.text
    assert MEMBER_ID in caplog.text


# ── Full notify() integration ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_integration_calls_twilio_dispatch(twilio_settings, mock_twilio_client):
    """End-to-end: notify() passes rate limit → _twilio_dispatch() → messages.create()."""
    _, client_instance = mock_twilio_client
    svc = NotificationService()
    notif = make_notification(channel=NotificationChannel.WHATSAPP)

    result = await svc.notify(notif)

    assert result is True
    assert notif.sent is True
    assert notif.sent_at is not None
    client_instance.messages.create.assert_called_once()
    _, kwargs = client_instance.messages.create.call_args
    assert kwargs["to"] == f"whatsapp:{PHONE}"


@pytest.mark.asyncio
async def test_notify_multiple_members_dispatches_each(twilio_settings, mock_twilio_client):
    """Each member in target_member_ids gets their own Twilio call."""
    twilio_settings.member_phone_map = {
        "mbr_papa_003": "+917989975430",
        "mbr_mama_001": "+919876543211",
    }
    _, client_instance = mock_twilio_client
    svc = NotificationService()

    notif = Notification(
        household_id=HH_ID,
        target_member_ids=["mbr_papa_003", "mbr_mama_001"],
        channel=NotificationChannel.WHATSAPP,
        source=ActionSource.RULE_ENGINE,
        language="english",
        message="Group alert",
    )

    result = await svc.notify(notif)

    assert result is True
    assert client_instance.messages.create.call_count == 2
    called_tos = {c.kwargs["to"] for c in client_instance.messages.create.call_args_list}
    assert called_tos == {"whatsapp:+917989975430", "whatsapp:+919876543211"}
