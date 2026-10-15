"""Database engine, connection pooling, and session management."""

from collections.abc import Generator
from sqlalchemy import create_engine, event, text
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
    """Create all database tables and ensure backward compatible schema columns."""
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)

    # Lightweight migration check for SQLite
    try:
        with eng.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(projects)"))
            columns = [row[1] for row in res.fetchall()]
            if columns and "readme_content" not in columns:
                conn.execute(text("ALTER TABLE projects ADD COLUMN readme_content TEXT"))
                conn.commit()
                logger.info("Migrated projects table: added 'readme_content' column.")
    except Exception as exc:
        logger.debug("Schema migration notice: %s", exc)

    logger.info("Database initialized successfully at %s", eng.url)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to yield a database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
