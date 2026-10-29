from pathlib import Path
from typing import Any, cast

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import ServiceError
from app.db.models import Base

# Keep this in sync with the migration graph. A regression test compares the
# runtime guard with Alembic's actual head so a newly added ORM column cannot
# be deployed while an older SQLite schema is still reported as ready.
ALEMBIC_HEAD = "0007_qdrant_snapshots"


class Database:
    def __init__(
        self,
        url: str,
        *,
        create_for_tests: bool = False,
        pool_size: int = 4,
        max_overflow: int = 2,
        pool_timeout_seconds: int = 10,
        pool_recycle_seconds: int = 300,
        connect_timeout_seconds: int = 10,
    ) -> None:
        self._ensure_parent(url)
        parsed_url = make_url(url)
        self.backend = parsed_url.get_backend_name()
        engine_options: dict[str, Any] = {"pool_pre_ping": True}
        if self.backend == "sqlite":
            engine_options["connect_args"] = {"check_same_thread": False}
        else:
            engine_options.update(
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout_seconds,
                pool_recycle=pool_recycle_seconds,
                pool_use_lifo=True,
                connect_args={
                    "connect_timeout": connect_timeout_seconds,
                    "application_name": "bkquiz-rag",
                },
            )
        self.engine = create_engine(url, **engine_options)
        if self.backend == "sqlite":
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

    @classmethod
    def from_settings(cls, settings: Any, *, create_for_tests: bool = False) -> "Database":
        return cls(
            settings.database_url,
            create_for_tests=create_for_tests,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout_seconds=settings.database_pool_timeout_seconds,
            pool_recycle_seconds=settings.database_pool_recycle_seconds,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
