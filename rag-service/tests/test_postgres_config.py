import pytest
from pydantic import ValidationError
from sqlalchemy.pool import QueuePool

from app.core.config import Settings
from app.db.database import Database

BASE = {
    "gemini_model": "test-model",
    "spring_boot_internal_api_key": "test-internal-key",
    "index_lock_mode": "redis",
}


def test_production_requires_postgresql() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL/Neon"):
        Settings(**BASE, app_env="production", database_url="sqlite:///data/rag.db")


def test_production_requires_database_tls() -> None:
    with pytest.raises(ValidationError, match="sslmode"):
        Settings(
            **BASE,
            app_env="production",
            database_url="postgresql+psycopg://user:password@example.neon.tech/rag",
        )


def test_postgres_requires_psycopg_driver_scheme() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        Settings(
            **BASE,
            database_url="postgresql://user:password@example.neon.tech/rag?sslmode=require",
        )


def test_postgres_engine_uses_configured_pool_without_connecting() -> None:
    database = Database(
        "postgresql+psycopg://user:password@example.invalid/rag?sslmode=require",
        pool_size=3,
        max_overflow=1,
    )
    try:
        assert database.backend == "postgresql"
        assert isinstance(database.engine.pool, QueuePool)
        assert database.engine.pool.size() == 3
        assert database.engine.pool._max_overflow == 1
    finally:
        database.dispose()
