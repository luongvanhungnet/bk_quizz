import time
from typing import Any

from app.core.exceptions import ServiceError

RATE_LIMIT_INCREMENT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RedisRateLimiter:
    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    def check(self, scope: str, owner_key: str, limit: int, window_seconds: int = 60) -> None:
        bucket = int(time.time() // window_seconds)
        key = f"rag:rate:{scope}:{owner_key}:{bucket}"
        try:
            count = int(
                self._redis.eval(RATE_LIMIT_INCREMENT, 1, key, window_seconds + 1)
            )
        except Exception as error:
            raise ServiceError(
                503, "RATE_LIMIT_STORE_UNAVAILABLE", "Bộ giới hạn truy cập tạm thời không khả dụng.",
                retryable=True, retry_after_seconds=5,
            ) from error
        if count > limit:
            retry_after = window_seconds - (int(time.time()) % window_seconds)
            raise ServiceError(
                429, "RATE_LIMITED", "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
                retryable=True, retry_after_seconds=max(1, retry_after),
            )


class NoopRateLimiter:
    def check(self, scope: str, owner_key: str, limit: int, window_seconds: int = 60) -> None:
        return None
