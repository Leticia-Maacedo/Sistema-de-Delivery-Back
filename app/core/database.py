"""Conexao com o PostgreSQL e sessao do SQLAlchemy."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Classe base de todos os Models."""


def get_db() -> Generator[Session, None, None]:
    """Dependencia do FastAPI: abre uma sessao por requisicao e fecha ao final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
