from logging.config import fileConfig
from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from app.db.models import Base
from dotenv import dotenv_values


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
env_file = dotenv_values(PROJECT_ROOT / ".env")
database_url = os.environ.get("DATABASE_URL") or env_file.get("DATABASE_URL") or "sqlite:///data/rag.db"
config.set_main_option("sqlalchemy.url", str(database_url))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    is_sqlite = make_url(config.get_main_option("sqlalchemy.url")).get_backend_name() == "sqlite"
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
