"""
Database Engine & Session Management for Apex-Research.

Configures connection pooling and session lifecycle for PostgreSQL / SQLite.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.models import Base

# Default to SQLite for local development/testing, PostgreSQL in production
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///.cache/apex_research.db")

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
