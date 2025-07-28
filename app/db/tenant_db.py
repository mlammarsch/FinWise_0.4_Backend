import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# SQLAlchemy base for tenant-specific tables
Base = declarative_base()

# Importiere die korrekte Pfad-Konfiguration aus config.py
from ..config import TENANT_DATABASE_DIR

TENANT_DB_DIR = TENANT_DATABASE_DIR
TENANT_DB_PREFIX = "finwiseTenantDB_"

# get_tenant_db_url wurde nach database.py verschoben - verwende den Import von dort

def create_tenant_db_engine(tenant_uuid: str):
    from .database import get_or_create_tenant_engine
    return get_or_create_tenant_engine(tenant_uuid)

TenantSessionLocal = sessionmaker(autocommit=False, autoflush=False)

def create_all_tenant_tables(engine):
    Base.metadata.create_all(bind=engine)

def init_tenant_db(tenant_uuid: str):
    """Initialisiert die Datenbank für einen Mandanten."""
    if not os.path.exists(TENANT_DB_DIR):
        os.makedirs(TENANT_DB_DIR)

    engine = create_tenant_db_engine(tenant_uuid)
    db_path = engine.url.database

    try:
        create_all_tenant_tables(engine)
        return engine
    except Exception as e:
        raise

def delete_tenant_db_file(tenant_uuid: str) -> bool:
    from .database import get_tenant_db_url
    db_url = get_tenant_db_url(tenant_uuid)
    db_path = db_url.replace("sqlite:///", "")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            return True
        except OSError as e:
            return False
    return False

if __name__ == "__main__":
    test_tenant_uuid = "test_tenant_12345"
    print(f"Versuche, Datenbank für Mandant {test_tenant_uuid} zu initialisieren...")
    init_tenant_db(test_tenant_uuid)
    delete_tenant_db_file(test_tenant_uuid)

    test_tenant_uuid_2 = "another_tenant_67890"
    print(f"Versuche, Datenbank für Mandant {test_tenant_uuid_2} zu initialisieren...")
    init_tenant_db(test_tenant_uuid_2)
    delete_tenant_db_file(test_tenant_uuid_2)
