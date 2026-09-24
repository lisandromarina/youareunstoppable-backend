from collections.abc import Generator
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from src.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _uses_transaction_pooler(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.port == 6543 or host.endswith("pooler.supabase.com")


def _create_engine(url: str):
    if _uses_transaction_pooler(url):
        return create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})
    return create_engine(url, pool_pre_ping=True)


engine = _create_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
