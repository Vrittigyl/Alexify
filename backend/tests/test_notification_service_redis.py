import time
import pytest
from unittest.mock import AsyncMock, patch
from redis.exceptions import TimeoutError as RedisTimeoutError

from schemas.actions import Notification
from schemas.enums import NotificationChannel
from services.notification_service import NotificationService
from db.redis_client import redis_client
from schemas.enums import NotificationChannel, ActionSource

HH_ID = "hh_xk92p_sharma"

def make_notification(member_id="mbr_rohan_005") -> Notification:
    return Notification(
        household_id=HH_ID,
        target_member_ids=[member_id],
        channel=NotificationChannel.MOBILE_PUSH,
        source=ActionSource.RULE_ENGINE,
        language="english",
        message="Test Notification",
        title="Test",
    )

@pytest.fixture(autouse=True)
async def mock_redis_env():
    # Setup mock redis
    redis_client.enabled = True
    redis_client.connected = True
    redis_client._redis = AsyncMock()
    redis_client.mode = "redis"
    
    # Store simulated redis sorted set as a simple dict mapping key to list of timestamps
    _mock_zset = {}
    
    async def mock_eval(script, numkeys, key, now_ms, window_ms, limit, member, window_secs):
        cutoff = now_ms - window_ms
        
        # 1. remove expired
        if key in _mock_zset:
            _mock_zset[key] = [t for t in _mock_zset[key] if t > cutoff]
        else:
            _mock_zset[key] = []
            
        # 2. count
        count = len(_mock_zset[key])
        
        # 3. check limit
        if count >= limit:
            return 0
            
        # 4. add new
        _mock_zset[key].append(now_ms)
        
        return 1
        
    redis_client._redis.eval.side_effect = mock_eval
    
    yield
    
    # Teardown
    redis_client.enabled = False
    redis_client.connected = False
    redis_client.mode = "fallback_memory"
    redis_client._redis = None

@pytest.mark.asyncio
async def test_notification_multipod_redis_on():
    service_a = NotificationService()
    service_b = NotificationService()
    
    # Send 2 notifications to member via service A
    for _ in range(2):
        notif = make_notification()
        result = await service_a.notify(notif)
        assert result is True
        assert notif.rate_limited is False
        
    # Send 1 notification to member via service B
    notif = make_notification()
    result = await service_b.notify(notif)
    assert result is True
    assert notif.rate_limited is False
        
    # Send 4th notification via service B - should be blocked
    notif = make_notification()
    result = await service_b.notify(notif)
    assert result is False
    assert notif.rate_limited is True

@pytest.mark.asyncio
async def test_notification_redis_timeout_fallback():
    redis_client._redis.eval.side_effect = RedisTimeoutError("Timeout")
    
    service = NotificationService()
    
    # First notification triggers timeout, falls back to memory, allowed
    notif = make_notification()
    result = await service.notify(notif)
    assert result is True
    assert redis_client.mode == "fallback_memory"
    
    # Send 2 more (total 3 limit)
    for _ in range(2):
        notif = make_notification()
        result = await service.notify(notif)
        assert result is True
        
    # 4th should be blocked by memory fallback
    notif = make_notification()
    result = await service.notify(notif)
    assert result is False
    assert notif.rate_limited is True

@pytest.mark.asyncio
async def test_notification_boundary():
    service = NotificationService()
    
    # Send 3 allowed requests
    for _ in range(3):
        notif = make_notification("mbr_boundary_test")
        result = await service.notify(notif)
        assert result is True
        
    # Send 4th request - blocked
    notif = make_notification("mbr_boundary_test")
    result = await service.notify(notif)
    assert result is False
    
    # Advance clock by patching time in NotificationService (fallback uses monotonic) AND Redis (uses time.time)
    import time
    future_time = time.time() + 1000
    future_monotonic = time.monotonic() + 1000
    with patch('time.time', return_value=future_time), patch('time.monotonic', return_value=future_monotonic):
        # Send 5th request - allowed again
        notif = make_notification("mbr_boundary_test")
        result = await service.notify(notif)
        assert result is True
