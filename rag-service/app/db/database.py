from pathlib import Path
from typing import Any, cast

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import ServiceError
from app.db.models import Base

# Keep this in sync with the migration graph. A regression test compares the
# runtime guard with Alembic's actual head so a newly added ORM column cannot
# be deployed while an older SQLite schema is still reported as ready.
ALEMBIC_HEAD = "0005_document_reindex"


class Database:
    def __init__(self, url: str, *, create_for_tests: bool = False) -> None:
        self._ensure_parent(url)
        self.engine: Engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        event.listen(self.engine, "connect", self._configure_sqlite)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        if create_for_tests:
            Base.metadata.create_all(self.engine)

    @staticmethod
    def _ensure_parent(url: str) -> None:
        prefix = "sqlite:///"
        if url.startswith(prefix):
            value = url[len(prefix) :]
            if value and value != ":memory:":
                Path(value).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _configure_sqlite(connection: object, _: object) -> None:
        cursor = cast(Any, connection).cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=-65536")
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.close()

    def validate_migrated(self) -> None:
        inspector = inspect(self.engine)
        if "documents" not in inspector.get_table_names() or "alembic_version" not in inspector.get_table_names():
            raise ServiceError(
                503,
                "DATABASE_MIGRATION_REQUIRED",
                "Cơ sở dữ liệu RAG chưa được migration.",
            )
        with self.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        if revision != ALEMBIC_HEAD:
            raise ServiceError(
                503,
                "DATABASE_MIGRATION_REQUIRED",
                "Phiên bản cơ sở dữ liệu RAG chưa tương thích.",
            )

    def session(self) -> Session:
        return self.session_factory()

    def dispose(self) -> None:
        self.engine.dispose()
