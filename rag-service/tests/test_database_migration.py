from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.exceptions import ServiceError
from app.db.database import ALEMBIC_HEAD, Database


def test_alembic_creates_documents_and_partial_unique_index(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert "documents" in inspector.get_table_names()
    indexes = {item["name"]: item for item in inspector.get_indexes("documents")}
    assert indexes["uq_documents_owner_hash_active"]["unique"] == 1
    with engine.connect() as connection:
        assert connection.execute(text("select version_num from alembic_version")).scalar_one() == ALEMBIC_HEAD
    job_columns = {item["name"] for item in inspector.get_columns("indexing_jobs")}
    job_indexes = {item["name"]: item for item in inspector.get_indexes("indexing_jobs")}
    assert "operation" in job_columns
    assert job_indexes["uq_indexing_jobs_document_active"]["unique"] == 1
    columns = {item["name"] for item in inspector.get_columns("documents")}
    assert {"math_extraction_status", "math_formula_count", "math_warning_count"} <= columns
    assert "math_extractions" in inspector.get_table_names()
    assert {
        "documents",
        "indexing_jobs",
        "audit_events",
        "vector_index_snapshots",
    }.issubset(inspector.get_table_names())
    indexes = {item["name"] for item in inspector.get_indexes("indexing_jobs")}
    assert "idx_indexing_jobs_pending_updated" in indexes
    assert "idx_indexing_jobs_running_heartbeat" in indexes


def test_runtime_expected_revision_matches_alembic_head() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    assert ALEMBIC_HEAD == ScriptDirectory.from_config(config).get_current_head()


def test_runtime_rejects_database_at_previous_revision(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "outdated.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0003_performance_indexes")
    database = Database(database_url)

    with pytest.raises(ServiceError) as captured:
        database.validate_migrated()

    assert captured.value.code == "DATABASE_MIGRATION_REQUIRED"
    database.dispose()
