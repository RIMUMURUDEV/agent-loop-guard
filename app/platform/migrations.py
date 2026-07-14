from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command


def alembic_config(storage_url: str) -> Config:
    script_location = Path(__file__).with_name("alembic")
    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", storage_url.replace("%", "%%"))
    return config


def migrate_database(engine, storage_url: str) -> None:
    config = alembic_config(storage_url)
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        # v0.1 databases were created from the same SQLAlchemy metadata.
        command.stamp(config, "0001_initial")
    command.upgrade(config, "head")
