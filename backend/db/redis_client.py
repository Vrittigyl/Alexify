import logging
import asyncio
import time
import uuid
from typing import Any, Dict

import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError

from config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis Foundation Layer (Phase 3.1)
    Provides an async connection pool and graceful degradation tracking.
    """

    def __init__(self):
        self.enabled: bool = settings.redis_enabled
        self.connected: bool = False
        self.mode: str = "fallback_memory"
        self.last_error: str | None = None
        self._pool: redis.ConnectionPool | None = None
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        if not self.enabled:
            logger.info("Redis: disabled by configuration")
            self.mode = "fallback_memory"
            self.connected = False
            return

        try:
            self._pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                socket_timeout=settings.redis_socket_timeout,
                socket_connect_timeout=settings.redis_connect_timeout,
                health_check_interval=settings.redis_health_check_interval,
                decode_responses=True,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            
            # Fail fast on startup with a ping
            await self._redis.ping()
            
            self.connected = True
            self.mode = "redis"
            self.last_error = None
            logger.info("Redis: connected successfully")
            
        except (ConnectionError, TimeoutError) as e:
            self.connected = False
            self.mode = "fallback_memory"
            self.last_error = str(e)
            logger.warning("Redis: unavailable, running in fallback memory mode")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
            self._redis = None
            self.connected = False

    async def acquire_idempotency_lock(self, key: str, ttl_secs: int) -> bool | None:
        """
        Attempts to acquire a distributed idempotency lock using SET NX EX.
        Returns:
            True if lock was acquired (command should execute).
            False if lock was denied (duplicate command).
            None if Redis is unavailable (fallback to memory).
        """
        if not self.enabled or not self.connected or not self._redis:
            self.mode = "fallback_memory"
            return None
            
        try:
            # SET key "1" NX EX ttl_secs
            result = await self._redis.set(key, "1", nx=True, ex=ttl_secs)
            return bool(result)
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis idempotency lock failed for {key}: {e}. Falling back to memory.")
            self.connected = False
            self.mode = "fallback_memory"
            self.last_error = str(e)
            return None

    async def check_rate_limit(self, key: str, limit: int, window_secs: int) -> bool | None:
        """
        Distributed sliding window rate limiter using Redis ZSETs and Lua.
        Returns:
            True if allowed
            False if rate-limited
            None if Redis is unavailable (fallback to memory)
        """
        if not self.enabled or not self.connected or not self._redis:
            self.mode = "fallback_memory"
            return None

        # Lua script for atomic sliding window rate limit
        script = """
        local key = KEYS[1]
        local now_ms = tonumber(ARGV[1])
        local window_ms = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local member = ARGV[4]
        local window_secs = tonumber(ARGV[5])
        
        local cutoff = now_ms - window_ms
        
        -- 1. Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
        
        -- 2. Count active entries
        local count = redis.call('ZCARD', key)
        
        -- 3. If count >= limit, reject
        if count >= limit then
            return 0
        end
        
        -- 4. Add current timestamp
        redis.call('ZADD', key, now_ms, member)
        
        -- 5. Set expiry to auto-cleanup the key
        redis.call('EXPIRE', key, window_secs)
        
        -- 6. Allowed
        return 1
        """
        
        now_ms = int(time.time() * 1000)
        window_ms = window_secs * 1000
        member = f"{now_ms}:{uuid.uuid4().hex}"
        
        try:
            result = await self._redis.eval(
                script, 
                1, 
                key, 
                now_ms, 
                window_ms, 
                limit, 
                member, 
                window_secs
            )
            return bool(result)
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis rate limit failed for {key}: {e}. Falling back to memory.")
            self.connected = False
            self.mode = "fallback_memory"
            self.last_error = str(e)
            return None

    def get_health(self) -> Dict[str, Any]:
        """
        Returns the detailed Redis health status for the /health endpoint.
        """
        # Read pubsub connection status if the global pubsub client exists
        pubsub_connected = False
        try:
            from db.redis_client import redis_pubsub_client
            pubsub_connected = redis_pubsub_client.connected
        except ImportError:
            pass

        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "pubsub_connected": pubsub_connected,
            "mode": "distributed" if (self.connected and pubsub_connected) else self.mode,
            "last_error": self.last_error
        }


# Module-level singletons
redis_client = RedisClient()
redis_pubsub_client = RedisClient()
