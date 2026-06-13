import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.presence_service import PresenceService
from db.redis_client import redis_client

HH_ID = "hh_presence_test"

@pytest.fixture(autouse=True)
def clean_redis_mock():
    """Reset the redis mock before each test."""
    pipe_mock = MagicMock()
    pipe_mock.set = MagicMock(return_value=pipe_mock)
    pipe_mock.publish = MagicMock(return_value=pipe_mock)
    pipe_mock.execute = AsyncMock()
    
    class PipelineContext:
        async def __aenter__(self):
            return pipe_mock
        async def __aexit__(self, exc_type, exc, tb):
            pass
            
    redis_mock = AsyncMock()
    redis_mock.pipeline = MagicMock(return_value=PipelineContext())
    
    redis_client._redis = redis_mock
    redis_client.enabled = True
    redis_client.connected = True
    
    yield
    
    redis_client._redis = None
    redis_client.enabled = False

@pytest.mark.asyncio
async def test_presence_redis_write_through():
    """Test that update() correctly issues a pipeline of SET and PUBLISH."""
    presence = PresenceService()
    
    # We must patch _fire_and_forget to actually await the coro so we can assert on it in the test,
    # or just await _push_to_redis directly to test the Redis part, and test update() locally.
    # To test update(), we can just wait a tiny bit since it uses create_task.
    
    presence.update(HH_ID, "mbr_test_1", room_id="living_room", is_home=True)
    
    # Let the event loop run the fire_and_forget task
    await asyncio.sleep(0.01)
    
    # Assert local memory is updated
    assert presence.is_home(HH_ID, "mbr_test_1") is True
    assert presence.get_member_room(HH_ID, "mbr_test_1") == "living_room"
    
    # Assert Redis pipeline was executed
    # Note: redis_client._redis is already mocked in conftest.py, we just need to ensure pipeline was called.
    # Since our fixture adds a mock pipeline, we can check if it was called.
    assert redis_client._redis.pipeline.called

@pytest.mark.asyncio
async def test_presence_fallback_no_redis():
    """Test that update() works seamlessly when Redis is unavailable or times out."""
    # Force _push_to_redis to throw an exception by removing the pipeline mock
    # or simulating redis_client._redis being None
    
    original_redis = redis_client._redis
    redis_client._redis = None
    
    try:
        presence = PresenceService()
        presence.update(HH_ID, "mbr_test_2", room_id="kitchen", is_home=True)
        
        # Local memory should still be updated
        assert presence.is_home(HH_ID, "mbr_test_2") is True
        
        presence.mark_left(HH_ID, "mbr_test_2")
        assert presence.is_home(HH_ID, "mbr_test_2") is False
    finally:
        redis_client._redis = original_redis

@pytest.mark.asyncio
async def test_presence_ttl_expiration():
    """Test that local memory correctly filters expired presence records."""
    presence = PresenceService(ttl_secs=1)
    presence.update(HH_ID, "mbr_test_3", room_id="kitchen", is_home=True)
    
    assert len(presence.get_all(HH_ID)) == 1
    
    # Wait for TTL to expire
    import time
    with patch('time.monotonic', return_value=time.monotonic() + 2):
        assert len(presence.get_all(HH_ID)) == 0
        assert presence.is_home(HH_ID, "mbr_test_3") is False
        assert presence.get_member_room(HH_ID, "mbr_test_3") is None

@pytest.mark.asyncio
async def test_presence_multipod_pubsub():
    """Test that start_subscriber processes Pub/Sub events correctly."""
    presence1 = PresenceService()
    presence2 = PresenceService()
    
    # Start the subscriber loop on presence2 but mock the listen
    import json
    
    # Mock pubsub listen to return one message, then throw asyncio.CancelledError to exit loop
    async def mock_listen():
        payload = json.dumps({
            "household_id": HH_ID,
            "member_id": "mbr_test_pubsub",
            "room_id": "bedroom",
            "is_home": True
        })
        yield {"type": "message", "data": payload}
        # Throw to exit the infinite loop gracefully in test
        raise asyncio.CancelledError()
        
    pubsub_mock = AsyncMock()
    pubsub_mock.listen = mock_listen
    pubsub_mock.subscribe = AsyncMock()
    
    redis_client._redis.pubsub = MagicMock(return_value=pubsub_mock)
    
    # Run subscriber until it hits CancelledError
    try:
        await presence2.start_subscriber()
    except asyncio.CancelledError:
        pass
        
    # Now presence2 should have updated its local memory based on the mock message
    assert presence2.is_home(HH_ID, "mbr_test_pubsub") is True
    assert presence2.get_member_room(HH_ID, "mbr_test_pubsub") == "bedroom"
