"""JSON cache helpers shared by all FastAPI workers through Redis."""

import json
from typing import Any

from app.core.config import settings
from app.core.redis import redis_client


async def get_cached_json(key: str) -> Any | None:
    value = await redis_client.get(key)
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        await redis_client.delete(key)
        return None


async def set_cached_json(key: str, value: Any) -> None:
    await redis_client.set(
        key,
        json.dumps(value, ensure_ascii=False),
        ex=settings.cache_ttl_seconds,
    )
