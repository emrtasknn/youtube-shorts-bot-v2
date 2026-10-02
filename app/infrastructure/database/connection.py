from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from app.config.settings import get_settings

settings=get_settings()
engine=create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_session() -> Session:
    return SessionLocal()

def check_database_connection() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
