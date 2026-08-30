import os

import pytest
from sqlalchemy import inspect

from app.db.database import Database


@pytest.mark.integration
def test_postgres_schema_and_partial_indexes() -> None:
    url = os.getenv("RAG_TEST_POSTGRES_URL", "").strip()
    if not url:
        pytest.skip("RAG_TEST_POSTGRES_URL is not configured")

    database = Database(url)
    try:
        database.validate_migrated()
        assert database.backend == "postgresql"
        indexes = {item["name"]: item for item in inspect(database.engine).get_indexes("indexing_jobs")}
        assert indexes["idx_indexing_jobs_pending_updated"]["dialect_options"]["postgresql_where"]
        assert indexes["idx_indexing_jobs_running_heartbeat"]["dialect_options"]["postgresql_where"]
        assert indexes["uq_indexing_jobs_document_active"]["unique"] is True
    finally:
        database.dispose()
