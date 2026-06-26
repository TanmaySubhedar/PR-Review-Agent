from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    # Migrate existing databases: add the fingerprint column if it was created
    # before this field existed. SQLite raises on duplicate column — that's fine,
    # it means the column is already there.
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE finding ADD COLUMN fingerprint TEXT"))
            conn.commit()
        except Exception:
            pass


def get_session():
    with Session(engine) as session:
        yield session
