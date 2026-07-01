from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .settings import DATABASE_URL
from .models import Base

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40,
    pool_timeout=30,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_lock(315803)"))
            try:
                Base.metadata.create_all(bind=connection)
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(315803)"))
        else:
            Base.metadata.create_all(bind=connection)
