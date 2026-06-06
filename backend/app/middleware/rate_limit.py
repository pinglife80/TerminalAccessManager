"""Rate limiting middleware using Redis sliding window with Sorted Sets"""
import time
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger
import redis.asyncio as aioredis
from typing import Optional

from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware based on Redis sliding window algorithm using Sorted Sets"""

    def __init__(self, app, redis_url: str = None):
        super().__init__(app)
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[aioredis.Redis] = None

    async def get_redis(self) -> aioredis.Redis:
        """Get or create Redis client"""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_rate_limit(self, path: str) -> int:
        """Get rate limit for a given path"""
        auth_paths = ["/auth/login", "/auth/register", "/auth/refresh"]
        for auth_path in auth_paths:
            if auth_path in path:
                return settings.AUTH_RATE_LIMIT_PER_MINUTE
        return settings.RATE_LIMIT_PER_MINUTE

    async def _check_rate_limit(self, client_id: str, path: str, rate_limit: int) -> tuple[bool, int]:
        """Check rate limit using sliding window algorithm with Redis Sorted Set.
        
        Returns (is_allowed, retry_after_seconds).
        """
        redis = await self.get_redis()
        key = f"rate_limit:{client_id}:{path}"
        now = time.time()
        window_start = now - 60  # 1 minute window

        # Use Redis pipeline for atomicity
        pipe = redis.pipeline()
        # Remove entries older than the window
        pipe.zremrangebyscore(key, 0, window_start)
        # Add current request with current timestamp as score
        pipe.zadd(key, {str(now): now})
        # Count requests in the current window
        pipe.zcard(key)
        # Set expiry on the key (cleanup after window)
        pipe.expire(key, 60)
        results = await pipe.execute()

        request_count = results[2]
        if request_count > rate_limit:
            # Calculate retry-after: time until oldest request in window expires
            oldest = await redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = int(oldest[0][1] + 60 - now) + 1
            else:
                retry_after = 60
            return False, max(retry_after, 1)

        return True, 0

    async def dispatch(self, request: Request, call_next):
        """Check rate limit before processing request"""
        # Skip rate limiting for health checks and metrics
        if request.url.path in ["/health", "/metrics", "/"]:
            return await call_next(request)

        # Skip non-API paths
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        client_id = self._get_client_id(request)
        rate_limit = self._get_rate_limit(request.url.path)

        try:
            is_allowed, retry_after = await self._check_rate_limit(client_id, request.url.path, rate_limit)

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for {client_id} on {request.url.path}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(retry_after)}
                )
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Allow request if Redis is unavailable

        response = await call_next(request)
        return response
