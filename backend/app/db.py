from sqlalchemy import Engine, event
from sqlmodel import create_engine

from app.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    """SQLite engine with foreign keys enforced (SQLite leaves them off by default)."""
    engine = create_engine(url or get_settings().database_url)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
