from collections.abc import Generator
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }


engine = create_engine(settings.database_url, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_database_url(url: str) -> dict[str, str]:
    """Parse SQLAlchemy URL into connection parts."""
    # Support postgresql+psycopg://user:pass@host:port/db
    normalized = url.replace("postgresql+psycopg://", "postgresql://", 1)
    normalized = normalized.replace("postgresql+psycopg2://", "postgresql://", 1)
    parsed = urlparse(normalized)
    dbname = (parsed.path or "/").lstrip("/") or "postgres"
    return {
        "scheme": parsed.scheme or "postgresql",
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": dbname,
    }


def admin_database_url(url: str, admin_db: str = "postgres") -> str:
    """URL pointing at the maintenance DB (usually `postgres`)."""
    parts = parse_database_url(url)
    user = parts["user"]
    password = parts["password"]
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql+psycopg://{auth}{parts['host']}:{parts['port']}/{admin_db}"
