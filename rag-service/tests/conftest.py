import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("GEMINI_MODEL", "test-model")
os.environ.setdefault("SPRING_BOOT_INTERNAL_API_KEY", "test-internal-key")

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_name="BKQuiz RAG Service",
        app_env="test",
        gemini_api_key="",
        gemini_model="test-model",
        spring_boot_internal_api_key="test-internal-key",
        gemini_retry_initial_delay_seconds=0,
        database_url=f"sqlite:///{(tmp_path / 'rag.db').as_posix()}",
        user_upload_dir=tmp_path / "uploads",
        user_index_dir=tmp_path / "indexes",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings=settings)) as test_client:
        yield test_client
