from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from ..config import SQLALCHEMY_DATABASE_URL, TENANT_DATABASE_DIR # Importiere die URL und das Verzeichnis aus config.py
from ..utils.logger import infoLog, errorLog, warnLog # Importiere den Logger
from ..models.financial_models import TenantBase # Importiere die korrekte Base für Mandanten-Tabellen

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base() # Dies ist die Base für die Haupt-DB (User, Tenant Metadaten)

def create_db_and_tables():
    # Diese Funktion erstellt Tabellen in der Haupt-DB
    from app.models.user_tenant_models import Base as UserTenantBase
    UserTenantBase.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_tenant_db_url(tenant_id: str) -> str:
    """Generiert die Datenbank-URL für einen bestimmten Mandanten."""
    db_filename = f"finwiseTenantDB_{tenant_id}.db"
    # Stelle sicher, dass TENANT_DATABASE_DIR korrekt behandelt wird, falls es None ist oder nicht existiert
    if not TENANT_DATABASE_DIR:
        errorLog("db.database", "TENANT_DATABASE_DIR is not configured.", {})
        raise ValueError("Tenant database directory is not configured.")

    # Erstelle das Verzeichnis, falls es nicht existiert.
    # Dies sollte idealerweise beim Anwendungsstart oder bei der ersten Tenant-Erstellung geschehen.
    # Hier zur Sicherheit nochmals, falls es aus irgendeinem Grund fehlt.
    if not os.path.exists(TENANT_DATABASE_DIR):
        try:
            os.makedirs(TENANT_DATABASE_DIR)
            infoLog("db.database", f"Created missing tenant database directory: {TENANT_DATABASE_DIR}", {})
        except OSError as e:
            errorLog("db.database", f"Error creating tenant database directory {TENANT_DATABASE_DIR}: {e}", {})
            raise # Fehler weiterwerfen, da ohne das Verzeichnis keine DBs erstellt werden können

    db_path = os.path.join(TENANT_DATABASE_DIR, db_filename)
    return f"sqlite:///{db_path}"

def create_tenant_specific_tables(tenant_id: str):
    """Erstellt alle Tabellen für eine spezifische Mandantendatenbank."""
    module_name = "db.database"
    infoLog(module_name, f"Attempting to create tables for tenant ID: {tenant_id}", {"tenant_id": tenant_id})
    try:
        tenant_db_url = get_tenant_db_url(tenant_id)

        # Die DB-Datei sollte bereits durch crud.create_tenant erstellt worden sein.
        # Hier prüfen wir es nicht explizit, da create_engine für SQLite die Datei erstellt, falls nicht vorhanden.
        # Ein Log in get_tenant_db_url oder crud.py sollte die Erstellung der Datei bestätigen.

        tenant_engine = create_engine(tenant_db_url, connect_args={"check_same_thread": False})

        # Importiere alle Modelle, die zu TenantBase gehören, damit sie registriert sind.
        # Der Import von TenantBase selbst sollte ausreichen, wenn financial_models.py
        # alle seine Modelle korrekt definiert und mit TenantBase verknüpft.
        # from app.models import financial_models # Ggf. expliziter Import aller Modelle hier

        TenantBase.metadata.create_all(bind=tenant_engine)
        infoLog(module_name, f"Successfully created tables for tenant ID: {tenant_id} in {tenant_db_url}", {"tenant_id": tenant_id, "db_url": tenant_db_url})
    except Exception as e:
        errorLog(module_name, f"Failed to create tables for tenant ID: {tenant_id}. Error: {str(e)}", {"tenant_id": tenant_id, "error": str(e)})
        raise

if __name__ == "__main__":
    # Erstellt die DB und Tabellen, wenn das Skript direkt ausgeführt wird
    print(f"Datenbank wird erstellt unter: {SQLALCHEMY_DATABASE_URL}")
    create_db_and_tables() # Erstellt nur Tabellen der Haupt-DB
    print("Haupt-Datenbank und Tabellen erfolgreich erstellt (falls nicht vorhanden).")
    # Das Erstellen von Mandanten-DBs und deren Tabellen geschieht on-demand.
