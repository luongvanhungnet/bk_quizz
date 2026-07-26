from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


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
        assert connection.execute(text("select version_num from alembic_version")).scalar_one() == "0003_performance_indexes"
    assert {"documents", "indexing_jobs", "audit_events"}.issubset(inspector.get_table_names())
    indexes = {item["name"] for item in inspector.get_indexes("indexing_jobs")}
    assert "idx_indexing_jobs_pending_updated" in indexes
    assert "idx_indexing_jobs_running_heartbeat" in indexes
