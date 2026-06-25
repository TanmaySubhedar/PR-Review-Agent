"""SQLite persistence. DB file lives at ~/.pr-agent/runs.db."""

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

_DB_DIR = Path.home() / ".pr-agent"
_DB_URL = f"sqlite:///{_DB_DIR / 'runs.db'}"


def _ensure_dir() -> None:
    _DB_DIR.mkdir(parents=True, exist_ok=True)


_ensure_dir()
engine = create_engine(_DB_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    """Create all tables. Safe to call multiple times (idempotent)."""
    # Import models so SQLModel.metadata knows about them.
    import pr_review_agent.models.db  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
