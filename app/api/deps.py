from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal

# TODO: Implement actual JWT token decoding and tenant_id extraction
async def get_current_tenant_id() -> str:
    """
    Platzhalter-Dependency, um die tenant_id des aktuellen Benutzers zu erhalten.
    MUSS durch eine echte Authentifizierungslogik ersetzt werden,
    die die tenant_id z.B. aus einem JWT-Token extrahiert.
    """
    # Für Testzwecke wird eine feste tenant_id zurückgegeben.
    # In einer realen Anwendung würde hier die tenant_id aus dem
    # authentifizierten Benutzerkontext (z.B. JWT-Token) extrahiert.
    return "tenant_test_001"

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
        engine = get_tenant_engine(tenant_id)
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
