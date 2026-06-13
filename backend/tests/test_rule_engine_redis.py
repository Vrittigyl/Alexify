import time
import pytest
from unittest.mock import AsyncMock, patch

from schemas import NormalizedEvent
from schemas.enums import ActionType, DeviceType, EventType, RuleType
from schemas.rules import Rule, RuleAction, RuleTrigger
from engines.rule_engine import RuleEvaluationEngine, RuleEngine
from db.redis_client import redis_client

HH_ID = "hh_xk92p_sharma"

def make_event(device_id="dev_water_motor_001") -> NormalizedEvent:
    return NormalizedEvent(
        household_id=HH_ID,
        event_type=EventType.DEVICE_STATE,
        device_type=DeviceType.WATER_MOTOR,
        device_id=device_id,
        payload={"tank_level_percent": 96, "state": "on"},
        requires_ai=False,
    )

def make_rule(rule_id="rl_idem_test_redis") -> Rule:
    return Rule(
        household_id="FLEET",
        rule_id=rule_id,
        rule_type=RuleType.SAFETY,
        trigger=RuleTrigger(
            event_type=EventType.DEVICE_STATE,
            device_type=DeviceType.WATER_MOTOR,
            field="tank_level_percent",
            op="gte",
            value=95,
        ),
        action=RuleAction(
            type=ActionType.DEVICE_COMMAND,
            command="turn_off",
            target_device_id="dev_water_motor_001",
        ),
        idempotency_window_secs=300,
    )

@pytest.fixture(autouse=True)
async def mock_redis_env():
    # Setup mock redis
    redis_client.enabled = True
    redis_client.connected = True
    redis_client._redis = AsyncMock()
    redis_client.mode = "redis"
    
    # Simple mock that stores locks locally in a dict to simulate Redis
    _mock_store = {}
    async def mock_set(key, value, nx=False, ex=None):
        if nx:
            if key in _mock_store:
                return None
            _mock_store[key] = value
            return True
        return True
        
    redis_client._redis.set.side_effect = mock_set
    
    yield
    
    # Teardown
    redis_client.enabled = False
    redis_client.connected = False
    redis_client.mode = "fallback_memory"
    redis_client._redis = None

@pytest.mark.asyncio
async def test_1_multipod_simulation_redis_on():
    """
    Test 1: Redis ON, Engine Instance A and Engine Instance B.
    Trigger A -> action generated
    Trigger B -> suppressed
    """
    rule = make_rule()
    event_a = make_event("dev_motor_A")
    event_b = make_event("dev_motor_B")

    engine_a = RuleEvaluationEngine()
    engine_b = RuleEvaluationEngine()

    # Trigger A
    result_a = await engine_a.evaluate(event_a, {}, rule)
    assert result_a.match is True

    # Trigger B (immediately after, using a separate instance to simulate a different pod)
    result_b = await engine_b.evaluate(event_b, {}, rule)
    assert result_b.match is False
    assert "Redis" in result_b.reason

@pytest.mark.asyncio
async def test_2_redis_off_fallback_works():
    """
    Test 2: Redis OFF. Fallback local cache still works exactly as before.
    """
    # Force Redis OFF
    redis_client.enabled = False
    redis_client.connected = False
    
    rule = make_rule()
    event = make_event()
    engine = RuleEvaluationEngine()

    # Trigger 1
    result_1 = await engine.evaluate(event, {}, rule)
    assert result_1.match is True

    # Trigger 2 (same instance fallback cache)
    result_2 = await engine.evaluate(event, {}, rule)
    assert result_2.match is False
    assert "Fallback" in result_2.reason

@pytest.mark.asyncio
async def test_3_redis_timeout_fallback_works():
    """
    Test 3: Redis timeout (ConnectionError).
    Expected: No exception, no 500, fallback cache used.
    """
    from redis.exceptions import TimeoutError as RedisTimeoutError
    # Force Redis to raise TimeoutError
    redis_client._redis.set.side_effect = RedisTimeoutError("Timeout connecting to Redis")
    
    rule = make_rule()
    event = make_event()
    engine = RuleEvaluationEngine()

    # Trigger 1: Should hit Redis, throw TimeoutError, log it, degrade to fallback mode, and mark local cache
    result_1 = await engine.evaluate(event, {}, rule)
    assert result_1.match is True
    assert redis_client.mode == "fallback_memory"
    assert redis_client.connected is False

    # Trigger 2: Should hit local fallback cache since Redis is now disabled for this client instance
    result_2 = await engine.evaluate(event, {}, rule)
    assert result_2.match is False
    assert "Fallback" in result_2.reason
