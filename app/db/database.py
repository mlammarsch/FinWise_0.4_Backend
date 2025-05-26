from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from ..config import SQLALCHEMY_DATABASE_URL # Importiere die URL aus config.py

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def create_db_and_tables():
    from app.models.user_tenant_models import Base as UserTenantBase
    UserTenantBase.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    # Erstellt die DB und Tabellen, wenn das Skript direkt ausgeführt wird
    print(f"Datenbank wird erstellt unter: {SQLALCHEMY_DATABASE_URL}")
    create_db_and_tables()
    print("Datenbank und Tabellen erfolgreich erstellt (falls nicht vorhanden).")
