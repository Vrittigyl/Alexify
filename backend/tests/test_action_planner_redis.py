import time
import pytest
from unittest.mock import AsyncMock, patch
from redis.exceptions import TimeoutError as RedisTimeoutError

from schemas import NormalizedEvent
from schemas.actions import Action
from schemas.enums import ActionSource, ActionType, DeviceType
from services.action_planner import ActionPlanner
from db.redis_client import redis_client

HH_ID = "hh_xk92p_sharma"

def make_device_action(device_id="dev_water_motor_001") -> Action:
    return Action(
        household_id=HH_ID,
        action_type=ActionType.DEVICE_COMMAND,
        source=ActionSource.RULE_ENGINE,
        device_id=device_id,
        command="turn_off",
        rule_id="rl_motor",
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
async def test_action_planner_multipod_redis_on():
    planner_a = ActionPlanner()
    planner_b = ActionPlanner()
    
    # Send 3 commands to planner A
    for _ in range(3):
        app = await planner_a.plan([make_device_action()])
        assert len(app) == 1
        
    # Send 2 commands to planner B
    for _ in range(2):
        app = await planner_b.plan([make_device_action()])
        assert len(app) == 1
        
    # Send 6th command to planner B - should be blocked
    app = await planner_b.plan([make_device_action()])
    assert len(app) == 0

@pytest.mark.asyncio
async def test_action_planner_redis_timeout_fallback():
    redis_client._redis.eval.side_effect = RedisTimeoutError("Timeout")
    
    planner = ActionPlanner()
    
    # First command triggers timeout, falls back to memory, allows action
    app = await planner.plan([make_device_action()])
    assert len(app) == 1
    assert redis_client.mode == "fallback_memory"
    
    # 5 more commands - the 5th (total 6th) should be blocked by memory fallback
    for i in range(4):
        app = await planner.plan([make_device_action()])
        assert len(app) == 1
        
    app = await planner.plan([make_device_action()])
    assert len(app) == 0

@pytest.mark.asyncio
async def test_action_planner_boundary():
    planner = ActionPlanner()
    
    # Send 5 allowed requests
    for _ in range(5):
        app = await planner.plan([make_device_action("dev_boundary_test")])
        assert len(app) == 1
        
    # Send 6th request - blocked
    app = await planner.plan([make_device_action("dev_boundary_test")])
    assert len(app) == 0
    
    # Advance clock by patching time in ActionPlanner (if it's using local memory) or Redis args
    import time
    future_time = time.time() + 5400
    with patch('time.time', return_value=future_time):
        # Send 7th request - allowed again
        app = await planner.plan([make_device_action("dev_boundary_test")])
        assert len(app) == 1
