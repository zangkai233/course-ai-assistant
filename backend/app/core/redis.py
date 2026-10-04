import redis.asyncio as redis

from app.core.config import settings


redis_pool = redis.BlockingConnectionPool.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    max_connections=settings.redis_max_connections,
    timeout=settings.redis_pool_wait_seconds,
)
redis_client = redis.Redis(connection_pool=redis_pool)


async def close_redis() -> None:
    await redis_client.aclose(close_connection_pool=True)
