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

def delete_tenant_database_file(tenant_id: str) -> bool:
    """
    Löscht die physische SQLite-Datei für einen Mandanten.
    Gibt True zurück wenn erfolgreich gelöscht oder Datei nicht existiert.
    """
    module_name = "db.database"
    try:
        if not TENANT_DATABASE_DIR:
            errorLog(module_name, "TENANT_DATABASE_DIR is not configured.", {"tenant_id": tenant_id})
            return False

        db_filename = f"finwiseTenantDB_{tenant_id}.db"
        db_path = os.path.join(TENANT_DATABASE_DIR, db_filename)

        if os.path.exists(db_path):
            os.remove(db_path)
            infoLog(module_name, f"Successfully deleted tenant database file: {db_path}",
                   {"tenant_id": tenant_id, "file_path": db_path})
            return True
        else:
            infoLog(module_name, f"Tenant database file does not exist: {db_path}",
                   {"tenant_id": tenant_id, "file_path": db_path})
            return True  # Datei existiert nicht = Ziel erreicht

    except OSError as e:
        errorLog(module_name, f"OS error deleting tenant database file for {tenant_id}",
                {"tenant_id": tenant_id, "error": str(e)})
        return False
    except Exception as e:
        errorLog(module_name, f"Unexpected error deleting tenant database file for {tenant_id}",
                {"tenant_id": tenant_id, "error": str(e)})
        return False

# Dictionary to track tenant engines for proper disposal
_tenant_engines = {}

# Hinzugefügte Funktion zum expliziten Schließen von Verbindungen einer Tenant-Engine
def dispose_tenant_engine(tenant_id: str):
    """Erstellt eine Engine für die Tenant-DB und ruft dispose() auf, um alle Verbindungen zu schließen."""
    module_name = "db.database"
    try:
        tenant_db_url = get_tenant_db_url(tenant_id)

        # Wenn wir bereits eine Engine für diesen Tenant haben, diese verwenden
        if tenant_id in _tenant_engines:
            engine_to_dispose = _tenant_engines[tenant_id]
            engine_to_dispose.dispose()
            del _tenant_engines[tenant_id]
            infoLog(module_name, f"Disposed existing connection pool for tenant ID: {tenant_id} ({tenant_db_url})",
                   {"tenant_id": tenant_id})
        else:
            # Erstelle eine Engine-Instanz und dispose sie sofort
            engine_to_dispose = create_engine(tenant_db_url, connect_args={"check_same_thread": False})
            engine_to_dispose.dispose()
            infoLog(module_name, f"Disposed connection pool for tenant ID: {tenant_id} ({tenant_db_url})",
                   {"tenant_id": tenant_id})

        # Zusätzlich: Versuche alle SQLite-Verbindungen zu schließen
        import gc
        gc.collect()  # Garbage Collection um sicherzustellen, dass alle Referenzen freigegeben werden
        infoLog(module_name, f"Disposed connection pool for tenant ID: {tenant_id} ({tenant_db_url})", {"tenant_id": tenant_id})
    except Exception as e:
        errorLog(module_name, f"Error disposing engine for tenant ID: {tenant_id}. Error: {str(e)}", {"tenant_id": tenant_id, "error": str(e)})
        # Fehler hier nicht weiter werfen, da der Löschversuch trotzdem stattfinden soll

def register_tenant_engine(tenant_id: str, engine):
    """Registriert eine Tenant-Engine für spätere ordnungsgemäße Entsorgung."""
    _tenant_engines[tenant_id] = engine

def get_or_create_tenant_engine(tenant_id: str):
    """Holt oder erstellt eine Tenant-Engine und registriert sie für spätere Entsorgung."""
    if tenant_id not in _tenant_engines:
        tenant_db_url = get_tenant_db_url(tenant_id)
        engine = create_engine(tenant_db_url, connect_args={"check_same_thread": False})
        _tenant_engines[tenant_id] = engine
    return _tenant_engines[tenant_id]

def reset_tenant_database(tenant_id: str) -> bool:
    """
    Setzt eine Mandanten-Datenbank zurück:
    1. Löscht die bestehende SQLite-Datei
    2. Erstellt eine neue Datei mit allen Tabellen
    """
    module_name = "db.database"
    infoLog(module_name, f"Resetting tenant database for ID: {tenant_id}", {"tenant_id": tenant_id})

    try:
        # 1. Bestehende Datei löschen
        file_deleted = delete_tenant_database_file(tenant_id)
        if not file_deleted:
            warnLog(module_name, f"Could not delete existing tenant database file for {tenant_id}",
                   {"tenant_id": tenant_id})

        # 2. Neue Datenbank mit Tabellen erstellen
        create_tenant_specific_tables(tenant_id)

        infoLog(module_name, f"Successfully reset tenant database for ID: {tenant_id}",
               {"tenant_id": tenant_id})
        return True

    except Exception as e:
        errorLog(module_name, f"Error resetting tenant database for {tenant_id}: {str(e)}",
                {"tenant_id": tenant_id, "error": str(e)})
        return False

if __name__ == "__main__":
    print(f"Datenbank wird erstellt unter: {SQLALCHEMY_DATABASE_URL}")
    create_db_and_tables()
    print("Haupt-Datenbank und Tabellen erfolgreich erstellt (falls nicht vorhanden).")
