from pathlib import Path

import pytest

from app.core.config import GeminiConfigConflictError, load_settings


def _write_env(path: Path, *, api_key: str, app_env: str = "development") -> None:
    path.write_text(
        "\n".join(
            [
                f"APP_ENV={app_env}",
                f"GEMINI_API_KEY={api_key}",
                "GEMINI_MODEL=gemini-3.5-flash-lite",
                "SPRING_BOOT_INTERNAL_API_KEY=test-internal-key",
                "DATABASE_URL=postgresql+psycopg://user:password@example.neon.tech/rag?sslmode=require",
                "VECTOR_STORE_BACKEND=qdrant",
                "QDRANT_URL=https://example.qdrant.io",
                "QDRANT_API_KEY=test-qdrant-key",
                "DOCUMENT_STORAGE_BACKEND=r2",
                "DOCUMENT_STORAGE_ENDPOINT=https://example.r2.cloudflarestorage.com",
                "DOCUMENT_STORAGE_BUCKET=test-bucket",
                "DOCUMENT_STORAGE_ACCESS_KEY=test-access-key",
                "DOCUMENT_STORAGE_SECRET_KEY=test-secret-key",
                "OLLAMA_ENABLED=false",
            ]
        ),
        encoding="utf-8",
    )


def test_development_rejects_conflicting_process_and_dotenv_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, api_key="dotenv-key")
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")
    monkeypatch.setenv("APP_ENV", "development")

    with pytest.raises(GeminiConfigConflictError) as raised:
        load_settings(env_file=env_file)

    assert raised.value.code == "GEMINI_CONFIG_CONFLICT"
    assert "process environment" in str(raised.value)
    assert "dotenv" in str(raised.value)
    assert "process-key" not in str(raised.value)
    assert "dotenv-key" not in str(raised.value)


def test_development_accepts_matching_process_and_dotenv_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, api_key="same-key")
    monkeypatch.setenv("GEMINI_API_KEY", "same-key")
    monkeypatch.setenv("APP_ENV", "development")

    settings = load_settings(env_file=env_file)

    assert settings.gemini_api_key == "same-key"


def test_production_keeps_process_environment_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, api_key="dotenv-key", app_env="production")
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")
    monkeypatch.setenv("APP_ENV", "production")

    settings = load_settings(env_file=env_file)

    assert settings.gemini_api_key == "process-key"
