"""
Database Engine & Session Management for Apex-Research.

Configures connection pooling and session lifecycle for PostgreSQL / SQLite.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import get_settings
from app.db.models import Base

# Single source of truth for the connection string is app/config.py
# (Settings.database_url), which still honors the DATABASE_URL env var via
# pydantic-settings. Defaults to SQLite for local dev/testing; point it at
# Supabase's Postgres in production.
DATABASE_URL = get_settings().database_url

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Creates database tables if they do not exist."""
    os.makedirs(".cache", exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db_session() -> Session:
    """Dependency helper for retrieving a transactional DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
