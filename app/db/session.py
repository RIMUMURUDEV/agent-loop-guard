from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import AppConfig
from app.db.models import Base
from app.db.repository import ensure_seed_data
from app.platform.migrations import migrate_database


def build_engine(config: AppConfig):
    config.ensure_storage_parent()
    kwargs = {"future": True}
    if config.storage_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if config.storage_url == "sqlite:///:memory:":
            kwargs["poolclass"] = StaticPool
    engine = create_engine(config.storage_url, **kwargs)
    if config.storage_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def build_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(engine, config: AppConfig) -> None:
    migrate_database(engine, config.storage_url)
    # create_all is retained as a compatibility safety net for pre-v0.2 databases.
    Base.metadata.create_all(engine)
    if config.storage_url.startswith("sqlite"):
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    factory = build_session_factory(engine)
    with factory() as db:
        ensure_seed_data(db, config)


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.SessionLocal
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
