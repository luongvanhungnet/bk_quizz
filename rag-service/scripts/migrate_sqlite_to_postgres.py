"""Copy RAG metadata from SQLite to a migrated PostgreSQL/Neon database.

The service API, Celery worker and beat must be stopped while this script runs.
Connection strings are read from environment variables so credentials are not
placed in shell history.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import Engine, make_url

from app.db.database import ALEMBIC_HEAD

TABLES = (
    "documents",
    "math_extractions",
    "indexing_jobs",
    "audit_events",
    "vector_index_snapshots",
)


def _chunks(rows: list[dict[str, Any]], size: int = 500) -> Iterator[list[dict[str, Any]]]:
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def _required_url(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Thiếu biến môi trường {name}.")
    return value


def _validate_urls(source_url: str, target_url: str) -> None:
    if make_url(source_url).get_backend_name() != "sqlite":
        raise SystemExit("RAG_MIGRATION_SOURCE_URL phải là SQLite.")
    if make_url(target_url).get_backend_name() != "postgresql":
        raise SystemExit("RAG_MIGRATION_TARGET_URL phải là PostgreSQL.")


def _validate_target(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    missing = set(TABLES) - tables
    if missing or "alembic_version" not in tables:
        raise SystemExit("Neon chưa được chạy Alembic đầy đủ.")
    with engine.connect() as connection:
        revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    if revision != ALEMBIC_HEAD:
        raise SystemExit(
            f"Neon đang ở revision {revision}; cần alembic upgrade tới {ALEMBIC_HEAD}."
        )


def _validate_source(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    missing = set(TABLES) - tables
    if missing or "alembic_version" not in tables:
        raise SystemExit("SQLite source chưa được chạy Alembic đầy đủ.")
    with engine.connect() as connection:
        revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    if revision != ALEMBIC_HEAD:
        raise SystemExit(
            f"SQLite source đang ở revision {revision}; hãy chạy alembic upgrade head trước."
        )


def migrate(source_url: str, target_url: str, *, dry_run: bool = False) -> dict[str, int]:
    _validate_urls(source_url, target_url)
    source = create_engine(source_url)
    target = create_engine(target_url, pool_pre_ping=True)
    try:
        _validate_source(source)
        _validate_target(target)
        source_metadata = MetaData()
        target_metadata = MetaData()
        source_metadata.reflect(source, only=TABLES)
        target_metadata.reflect(target, only=TABLES)
        missing = set(TABLES) - set(source_metadata.tables)
        if missing:
            raise SystemExit(f"SQLite thiếu bảng: {', '.join(sorted(missing))}.")

        copied: dict[str, int] = {}
        with source.connect() as source_connection, target.begin() as target_connection:
            for name in TABLES:
                source_table: Table = source_metadata.tables[name]
                target_table: Table = target_metadata.tables[name]
                existing = target_connection.scalar(select(func.count()).select_from(target_table))
                if existing:
                    raise SystemExit(
                        f"Neon không rỗng: bảng {name} có {existing} bản ghi. Hủy migration để tránh ghi đè."
                    )
                rows = [dict(row) for row in source_connection.execute(select(source_table)).mappings()]
                copied[name] = len(rows)
                if not dry_run:
                    for batch in _chunks(rows):
                        target_connection.execute(target_table.insert(), batch)
            if dry_run:
                target_connection.rollback()
        if not dry_run:
            with target.connect() as connection:
                for name, expected in copied.items():
                    actual = connection.scalar(
                        select(func.count()).select_from(target_metadata.tables[name])
                    )
                    if actual != expected:
                        raise RuntimeError(
                            f"Sai số lượng sau migration tại {name}: expected={expected}, actual={actual}."
                        )
        return copied
    finally:
        source.dispose()
        target.dispose()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Migrate BKQuiz RAG metadata từ SQLite sang Neon.")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra, không ghi dữ liệu.")
    args = parser.parse_args()
    copied = migrate(
        _required_url("RAG_MIGRATION_SOURCE_URL"),
        _required_url("RAG_MIGRATION_TARGET_URL"),
        dry_run=args.dry_run,
    )
    mode = "Kiểm tra" if args.dry_run else "Đã sao chép"
    print(f"{mode} thành công: " + ", ".join(f"{name}={count}" for name, count in copied.items()))


if __name__ == "__main__":
    main()
