from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import contextvars
from typing import Dict

from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal
from app.utils.logger import infoLog, errorLog, debugLog

# Context variable to store the current tenant_id
current_tenant_context: contextvars.ContextVar[str] = contextvars.ContextVar('current_tenant_id')

def set_current_tenant_id(tenant_id: str):
    """
    Setzt die aktuelle Tenant-ID im Context.
    Wird von WebSocket-Endpunkten und anderen Services verwendet.
    """
    current_tenant_context.set(tenant_id)

def get_current_tenant_id_from_context() -> str:
    """
    Holt die aktuelle Tenant-ID aus dem Context.
    """
    try:
        return current_tenant_context.get()
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant-ID nicht im Kontext gefunden. Sie muss explizit übergeben werden."
        )

async def get_current_tenant_id(request: Request) -> str:
    """
    Dependency, um die tenant_id des aktuellen Benutzers zu erhalten.
    Versucht zuerst die Tenant-ID aus dem Context zu holen,
    falls das fehlschlägt, wird der X-Tenant-Id Header gelesen.
    """
    try:
        return get_current_tenant_id_from_context()
    except LookupError:
        # Fallback: Tenant-ID aus Header lesen
        if request and 'x-tenant-id' in request.headers:
            tenant_id = request.headers['x-tenant-id']
            debugLog('deps', f'Tenant-ID aus Header gelesen: {tenant_id}')
            return tenant_id

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant-ID nicht gefunden. Weder im Context noch im X-Tenant-Id Header."
        )

async def get_tenant_db_session(
    tenant_id: str = Depends(get_current_tenant_id)
) -> Session:
    """
    Stellt eine mandantenspezifische SQLAlchemy-Datenbank-Session bereit.

    Diese Dependency verwendet die `get_current_tenant_id`-Dependency, um die
    ID des aktuellen Mandanten zu erhalten und konfiguriert dann eine
    Datenbank-Session, die auf die Datenbank dieses spezifischen Mandanten zugreift.

    Die Session wird nach Abschluss des Requests automatisch geschlossen.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Keine Mandanten-ID im Request gefunden oder Benutzer nicht authentifiziert.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        engine = create_tenant_db_engine(tenant_id)
        TenantSessionLocal.configure(bind=engine)
        db = TenantSessionLocal()
        yield db
    except Exception as e:
        # Hier könnte spezifischeres Fehlerlogging erfolgen
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Herstellen der Verbindung zur Mandanten-Datenbank: {str(e)}"
        )
    finally:
        if 'db' in locals() and db is not None:
            db.close()

# Dictionary to track active tenant database connections
_tenant_connections: Dict[str, Session] = {}

def get_tenant_db(tenant_id: str) -> Session:
    """
    Holt oder erstellt eine mandantenspezifische Datenbankverbindung.
    Diese Funktion wird für langlebige Verbindungen verwendet (z.B. WebSocket).
    """
    if tenant_id in _tenant_connections:
        return _tenant_connections[tenant_id]

    try:
        engine = create_tenant_db_engine(tenant_id)
        TenantSessionLocal.configure(bind=engine)
        db = TenantSessionLocal()
        _tenant_connections[tenant_id] = db

        debugLog(
            "deps",
            f"Created new tenant database connection for tenant {tenant_id}",
            {"tenant_id": tenant_id}
        )

        return db
    except Exception as e:
        errorLog(
            "deps",
            f"Error creating tenant database connection for {tenant_id}: {str(e)}",
            {"tenant_id": tenant_id, "error": str(e)}
        )
        raise

def close_tenant_db_connection(tenant_id: str) -> bool:
    """
    Schließt die Datenbankverbindung für einen spezifischen Mandanten.
    Wird aufgerufen, wenn ein Mandant sich abmeldet oder gelöscht wird.
    """
    if tenant_id not in _tenant_connections:
        debugLog(
            "deps",
            f"No active database connection found for tenant {tenant_id}",
            {"tenant_id": tenant_id}
        )
        return True

    try:
        db = _tenant_connections[tenant_id]
        db.close()
        del _tenant_connections[tenant_id]

        infoLog(
            "deps",
            f"Successfully closed database connection for tenant {tenant_id}",
            {"tenant_id": tenant_id}
        )

        return True
    except Exception as e:
        errorLog(
            "deps",
            f"Error closing database connection for tenant {tenant_id}: {str(e)}",
            {"tenant_id": tenant_id, "error": str(e)}
        )
        return False

def close_all_tenant_connections():
    """
    Schließt alle aktiven Mandanten-Datenbankverbindungen.
    Wird beim Herunterfahren des Servers aufgerufen.
    """
    tenant_ids = list(_tenant_connections.keys())
    for tenant_id in tenant_ids:
        close_tenant_db_connection(tenant_id)

    infoLog(
        "deps",
        f"Closed all tenant database connections ({len(tenant_ids)} connections)",
        {"closed_connections": len(tenant_ids)}
    )
