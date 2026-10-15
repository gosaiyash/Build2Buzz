"""Database engine, connection pooling, and session management."""

from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from src.publisher.core.config import settings
from src.publisher.core.logging_config import logger


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy database models."""
    pass


def get_engine(database_url: str | None = None):
    """Create SQLAlchemy engine with foreign key support enabled for SQLite."""
    url = database_url or settings.DATABASE_URL
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    engine = create_engine(
        url,
        connect_args=connect_args,
        echo=settings.DEBUG,
    )

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(target_engine=None) -> None:
    """Create all database tables."""
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)
    logger.info("Database initialized successfully at %s", eng.url)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to yield a database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
