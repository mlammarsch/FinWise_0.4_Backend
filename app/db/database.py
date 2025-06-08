from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from ..config import SQLALCHEMY_DATABASE_URL, TENANT_DATABASE_DIR
from ..utils.logger import infoLog, errorLog, warnLog
from ..models.financial_models import TenantBase

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

def get_tenant_db_url(tenant_id: str) -> str:
    """Generates the database URL for a specific tenant."""
    db_filename = f"finwiseTenantDB_{tenant_id}.db"
    if not TENANT_DATABASE_DIR:
        errorLog("db.database", "TENANT_DATABASE_DIR is not configured.", {})
        raise ValueError("Tenant database directory is not configured.")

    if not os.path.exists(TENANT_DATABASE_DIR):
        try:
            os.makedirs(TENANT_DATABASE_DIR)
            infoLog("db.database", f"Created missing tenant database directory: {TENANT_DATABASE_DIR}", {})
        except OSError as e:
            errorLog("db.database", f"Error creating tenant database directory {TENANT_DATABASE_DIR}: {e}", {})
            raise

    db_path = os.path.join(TENANT_DATABASE_DIR, db_filename)
    return f"sqlite:///{db_path}"

def create_tenant_specific_tables(tenant_id: str):
    """Creates all tables for a specific tenant database."""
    module_name = "db.database"
    infoLog(module_name, f"Attempting to create tables for tenant ID: {tenant_id}", {"tenant_id": tenant_id})
    try:
        tenant_db_url = get_tenant_db_url(tenant_id)
        tenant_engine = create_engine(tenant_db_url, connect_args={"check_same_thread": False})
        TenantBase.metadata.create_all(bind=tenant_engine)
        infoLog(module_name, f"Successfully created tables for tenant ID: {tenant_id} in {tenant_db_url}", {"tenant_id": tenant_id, "db_url": tenant_db_url})
    except Exception as e:
        errorLog(module_name, f"Failed to create tables for tenant ID: {tenant_id}. Error: {str(e)}", {"tenant_id": tenant_id, "error": str(e)})
        raise

if __name__ == "__main__":
    print(f"Datenbank wird erstellt unter: {SQLALCHEMY_DATABASE_URL}")
    create_db_and_tables()
    print("Haupt-Datenbank und Tabellen erfolgreich erstellt (falls nicht vorhanden).")
