"""
Veritabanı bağlantısı.
Varsayılan olarak SQLite kullanıyor - üretimde DATABASE_URL'i
postgresql://... şeklinde değiştirmen yeterli, kod tarafında
başka bir değişiklik gerekmez.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pipeline.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Tüm ORM modellerinin ortak tabanı (SQLAlchemy 2.0 stili)."""


def get_db():
    """FastAPI dependency olarak kullanılır: Depends(get_db)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
