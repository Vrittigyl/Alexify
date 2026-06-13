import asyncio
import json
import redis
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from main import ConnectionManager
from db.redis_client import redis_client, redis_pubsub_client

HH_ID = "hh_ws_test"

@pytest.fixture(autouse=True)
def clean_redis_mock():
    """Reset the redis mock before each test."""
    # We will just patch the redis clients directly for these tests
    original_redis = redis_client._redis
    original_pubsub = redis_pubsub_client._redis
    
    redis_mock = AsyncMock()
    redis_mock.publish = AsyncMock()
    
    pubsub_mock = AsyncMock()
    
    class PubSubObj:
        def __init__(self):
            self.subscribe = AsyncMock()
            self._messages = []
            
        async def listen(self):
            for m in self._messages:
                yield m
                
        def add_message(self, msg):
            self._messages.append(msg)
            
    pubsub_instance = PubSubObj()
    pubsub_mock.pubsub = MagicMock(return_value=pubsub_instance)
    
    redis_client._redis = redis_mock
    redis_client.enabled = True
    
    redis_pubsub_client._redis = pubsub_mock
    redis_pubsub_client.enabled = True
    redis_pubsub_client.connected = True
    
    yield
    
    redis_client._redis = original_redis
    redis_pubsub_client._redis = original_pubsub

@pytest.mark.asyncio
async def test_ws_multipod_fanout():
    """Test that publish_to_redis on Manager A reaches Manager B."""
    manager_a = ConnectionManager()
    manager_b = ConnectionManager()
    
    # Mock local broadcast to verify delivery
    manager_b._local_broadcast = AsyncMock()
    
    # Manager A publishes
    await manager_a._publish_to_redis(HH_ID, "TEST_EVENT", {"foo": "bar"})
    
    assert redis_client._redis.publish.called
    args, kwargs = redis_client._redis.publish.call_args
    assert args[0] == "saathi:v1:ws:broadcast"
    
    payload_json = json.loads(args[1])
    assert payload_json["origin_pod_id"] == manager_a.pod_id
    
    # Feed it to Manager B's subscriber
    redis_pubsub_client._redis.pubsub().add_message({
        "type": "message",
        "data": json.dumps(payload_json)
    })
    
    # Run subscriber for one tick by throwing CancelledError after listen
    async def mock_listen_throw():
        for m in redis_pubsub_client._redis.pubsub()._messages:
            yield m
        raise asyncio.CancelledError()
        
    redis_pubsub_client._redis.pubsub().listen = mock_listen_throw
    
    try:
        await manager_b.start_subscriber()
    except asyncio.CancelledError:
        pass
        
    manager_b._local_broadcast.assert_called_once_with(HH_ID, "TEST_EVENT", {"foo": "bar"})

@pytest.mark.asyncio
async def test_ws_self_echo_prevention():
    """Test that a pod ignores messages originating from itself."""
    manager_a = ConnectionManager()
    manager_a._local_broadcast = AsyncMock()
    
    # Construct a message originating from manager_a
    payload_json = {
        "household_id": HH_ID,
        "event_type": "TEST_EVENT",
        "data": {},
        "origin_pod_id": manager_a.pod_id
    }
    
    redis_pubsub_client._redis.pubsub().add_message({
        "type": "message",
        "data": json.dumps(payload_json)
    })
    
    async def mock_listen_throw():
        for m in redis_pubsub_client._redis.pubsub()._messages:
            yield m
        raise asyncio.CancelledError()
        
    redis_pubsub_client._redis.pubsub().listen = mock_listen_throw
    
    try:
        await manager_a.start_subscriber()
    except asyncio.CancelledError:
        pass
        
    # MUST NOT call local broadcast because origin_pod_id matched
    manager_a._local_broadcast.assert_not_called()

@pytest.mark.asyncio
async def test_ws_redis_outage_fallback():
    """Test that broadcast degrades gracefully and local broadcasts continue seamlessly."""
    manager = ConnectionManager()
    manager._local_broadcast = AsyncMock()
    
    # Force Redis to fail
    redis_client._redis.publish.side_effect = Exception("Redis connection lost")
    
    # Call public API broadcast
    await manager.broadcast(HH_ID, "TEST_EVENT", {})
    
    # Local broadcast MUST be called
    manager._local_broadcast.assert_called_once_with(HH_ID, "TEST_EVENT", {})

@pytest.mark.asyncio
async def test_ws_subscriber_reconnect():
    """Test that the subscriber loop uses backoff on failure."""
    manager = ConnectionManager()
    
    # Force the listen to throw an exception
    async def mock_listen_error():
        yield {"type": "subscribe"}
        raise redis.ConnectionError("Simulated pubsub disconnect")
        
    redis_pubsub_client._redis.pubsub().listen = mock_listen_error
    
    # We will patch asyncio.sleep to throw CancelledError so we can break the infinite while True
    # but we count how many times it was called to ensure backoff works.
    sleep_mock = AsyncMock(side_effect=asyncio.CancelledError())
    
    with patch('asyncio.sleep', sleep_mock):
        try:
            await manager.start_subscriber()
        except asyncio.CancelledError:
            pass
            
    # Sleep should be called with backoff=1 initially
    sleep_mock.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_ws_no_replication_loop():
    """Test that subscriber explicitly only calls _local_broadcast, not public broadcast."""
    manager = ConnectionManager()
    
    # This test asserts that subscriber's code doesn't call `self.broadcast()`
    import inspect
    source = inspect.getsource(manager.start_subscriber)
    assert "await self._local_broadcast(" in source
    assert "await self.broadcast(" not in source
