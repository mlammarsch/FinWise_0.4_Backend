from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import contextvars

from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal

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
        # Fallback für den Fall, dass kein Context gesetzt ist
        return "tenant_test_001"

async def get_current_tenant_id() -> str:
    """
    Dependency, um die tenant_id des aktuellen Benutzers zu erhalten.
    Versucht zuerst die Tenant-ID aus dem Context zu holen,
    falls das fehlschlägt, wird ein Fallback-Wert verwendet.
    """
    return get_current_tenant_id_from_context()

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
