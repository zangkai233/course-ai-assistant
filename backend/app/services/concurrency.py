import asyncio
import time
import uuid

from app.core.config import settings
from app.core.redis import redis_client


LLM_SLOT_KEY = "llm:active_leases"


ACQUIRE_SCRIPT = """
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local token = ARGV[4]

redis.call(
    "ZREMRANGEBYSCORE",
    KEYS[1],
    "-inf",
    now
)

local current = redis.call(
    "ZCARD",
    KEYS[1]
)

if current < limit then

    redis.call(
        "ZADD",
        KEYS[1],
        expires,
        token
    )

    local ttl =
        math.ceil((expires - now) / 1000) + 30

    redis.call(
        "EXPIRE",
        KEYS[1],
        ttl
    )

    return 1
end

return 0
"""


async def acquire_llm_slot() -> str | None:

    token = uuid.uuid4().hex

    deadline = (
        time.monotonic()
        + settings.llm_queue_wait_seconds
    )

    lease_ms = settings.llm_lease_seconds * 1000

    while time.monotonic() < deadline:

        now_ms = int(time.time() * 1000)

        expires_ms = now_ms + lease_ms

        acquired = await redis_client.eval(
            ACQUIRE_SCRIPT,
            1,
            LLM_SLOT_KEY,
            now_ms,
            expires_ms,
            settings.llm_max_concurrency,
            token,
        )

        if int(acquired) == 1:
            return token

        await asyncio.sleep(0.15)

    return None


async def release_llm_slot(token: str) -> None:

    await redis_client.zrem(
        LLM_SLOT_KEY,
        token,
    )
