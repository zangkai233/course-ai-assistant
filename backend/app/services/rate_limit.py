import time

from fastapi import HTTPException

from app.core.config import settings
from app.core.redis import redis_client


RATE_LIMIT_SCRIPT = """
local current = redis.call("INCR", KEYS[1])

if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end

return current
"""


async def enforce_rate_limit(student_id: str) -> None:

    minute_bucket = int(time.time() // 60)

    key = f"rate:{student_id}:{minute_bucket}"

    count = await redis_client.eval(
        RATE_LIMIT_SCRIPT,
        1,
        key,
        70,
    )

    if int(count) > settings.rate_limit_per_minute:

        raise HTTPException(
            status_code=429,
            detail="Too many messages. Please wait a moment.",
        )
