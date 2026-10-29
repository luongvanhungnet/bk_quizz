import pytest
from pydantic import ValidationError
from sqlalchemy.pool import QueuePool

from app.core.config import Settings
from app.db.database import Database

BASE = {
    "gemini_model": "test-model",
    "spring_boot_internal_api_key": "test-internal-key",
    "index_lock_mode": "redis",
    "vector_store_backend": "qdrant",
    "qdrant_url": "https://example.qdrant.io",
    "qdrant_api_key": "test-qdrant-key",
    "document_storage_backend": "r2",
    "document_storage_endpoint": "https://example.r2.cloudflarestorage.com",
    "document_storage_bucket": "test-bucket",
    "document_storage_access_key": "test-access-key",
    "document_storage_secret_key": "test-secret-key",
    "ollama_enabled": False,
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


def test_production_requires_qdrant_backend() -> None:
    with pytest.raises(ValidationError, match="VECTOR_STORE_BACKEND"):
        Settings(
            **{**BASE, "vector_store_backend": "faiss"},
            app_env="production",
            database_url=(
                "postgresql+psycopg://user:password@example.neon.tech/rag?sslmode=require"
            ),
        )


def test_production_requires_qdrant_https_and_key() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            **{**BASE, "qdrant_url": "http://qdrant:6333"},
            app_env="production",
            database_url=(
                "postgresql+psycopg://user:password@example.neon.tech/rag?sslmode=require"
            ),
        )


def test_production_requires_r2_and_disables_ollama() -> None:
    production_database = (
        "postgresql+psycopg://user:password@example.neon.tech/rag?sslmode=require"
    )
    with pytest.raises(ValidationError, match="DOCUMENT_STORAGE_BACKEND"):
        Settings(
            **{**BASE, "document_storage_backend": "local"},
            app_env="production",
            database_url=production_database,
        )
    with pytest.raises(ValidationError, match="OLLAMA_ENABLED"):
        Settings(
            **{**BASE, "ollama_enabled": True},
            app_env="production",
            database_url=production_database,
        )


def test_production_gcp_dispatch_requires_complete_configuration() -> None:
    with pytest.raises(ValidationError, match="Pub/Sub"):
        Settings(
            **BASE,
            app_env="production",
            database_url=(
                "postgresql+psycopg://user:password@example.neon.tech/rag?sslmode=require"
            ),
            job_dispatch_backend="gcp",
        )


def test_production_upstash_requires_tls_endpoint_and_credential() -> None:
    production_database = (
        "postgresql+psycopg://user:password@example.neon.tech/rag?sslmode=require"
    )
    with pytest.raises(ValidationError, match="rediss"):
        Settings(
            **BASE,
            app_env="production",
            database_url=production_database,
            cache_redis_provider="upstash",
            cache_redis_url="redis://default:password@example.upstash.io:6379",
        )

    settings = Settings(
        **BASE,
        app_env="production",
        database_url=production_database,
        cache_redis_provider="upstash",
        cache_redis_url="rediss://default:password@example.upstash.io:6379",
    )
    assert settings.cache_redis_provider == "upstash"
