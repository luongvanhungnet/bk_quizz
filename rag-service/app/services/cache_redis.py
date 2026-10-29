from typing import Any

from redis import Redis


def create_cache_redis(settings: Any) -> Redis:
    return Redis.from_url(
        settings.cache_redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        health_check_interval=30,
        max_connections=settings.cache_redis_max_connections,
    )
