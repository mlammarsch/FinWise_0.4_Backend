import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# SQLAlchemy base for tenant-specific tables
Base = declarative_base()

TENANT_DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tenant_databases"))
TENANT_DB_PREFIX = "finwiseTenantDB_"

def get_tenant_db_url(tenant_uuid: str) -> str:
    db_name = f"{TENANT_DB_PREFIX}{tenant_uuid}.db"
    return f"sqlite:///{os.path.join(TENANT_DB_DIR, db_name)}"

def create_tenant_db_engine(tenant_uuid: str):
    db_url = get_tenant_db_url(tenant_uuid)
    return create_engine(db_url, connect_args={"check_same_thread": False})

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
