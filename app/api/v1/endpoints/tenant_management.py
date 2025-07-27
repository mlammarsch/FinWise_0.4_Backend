from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict, Any
import os
import sqlite3
import shutil
from datetime import datetime

from app.db.database import get_db
from app.db.tenant_db import get_tenant_db_url, TENANT_DB_DIR, init_tenant_db
from app.api.deps import get_current_tenant_id
from app.models import schemas
from app.db import crud
from app.utils.logger import debugLog, infoLog, errorLog, warnLog

# Dependency für user_id aus tenant_id
async def get_current_user_id(
    tenant_id: str = Depends(get_current_tenant_id),
    main_db: Session = Depends(get_db)
) -> str:
    """
    Ermittelt die user_id aus der tenant_id.
    """
    tenant = crud.get_tenant(main_db, tenant_id=tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mandant nicht gefunden"
        )
    return tenant.user_id

# Dependency für user_id beim Import (ohne Mandanten-Kontext)
async def get_current_user_id_for_import(
    request: Request,
    main_db: Session = Depends(get_db)
) -> str:
    """
    Ermittelt die user_id für Import-Operationen direkt aus dem Request-Header.
    """
    # Versuche zuerst X-User-Id Header zu lesen
    user_id = request.headers.get("X-User-Id")

    if not user_id:
        # Fallback: Versuche über X-Tenant-Id einen User zu finden
        tenant_id = request.headers.get("X-Tenant-Id")
        if tenant_id:
            tenant = crud.get_tenant(main_db, tenant_id=tenant_id)
            if tenant:
                user_id = tenant.user_id

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User-ID nicht im Kontext gefunden. Sie muss explizit übergeben werden."
        )

    return user_id

MODULE_NAME = "TenantManagementAPI"

router = APIRouter()


@router.get("/export-database")
async def export_tenant_database(
    tenant_id: str
):
    # TenantId wird jetzt als Query-Parameter erwartet
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant-ID muss als Query-Parameter 'tenant_id' übergeben werden."
        )
    """
    Exportiert die SQLite-Datenbank des aktuellen Mandanten als Download.
    """
    debugLog(MODULE_NAME, f"Export-Request für Mandant {tenant_id}")

    try:
        # Pfad zur Mandanten-Datenbank ermitteln
        db_url = get_tenant_db_url(tenant_id)
        db_path = db_url.replace("sqlite:///", "")

        # Prüfen ob Datenbankdatei existiert
        if not os.path.exists(db_path):
            errorLog(
                MODULE_NAME,
                f"Datenbankdatei für Mandant {tenant_id} nicht gefunden",
                details={"tenant_id": tenant_id, "db_path": db_path}
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mandanten-Datenbank nicht gefunden"
            )

        # Mandantenname für Dateiname ermitteln
        main_db = next(get_db())
        try:
            tenant = crud.get_tenant(main_db, tenant_id=tenant_id)
            if not tenant:
                errorLog(
                    MODULE_NAME,
                    f"Mandant {tenant_id} nicht in Hauptdatenbank gefunden",
                    details={"tenant_id": tenant_id}
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Mandant nicht gefunden"
                )

            tenant_name = tenant.name
        finally:
            main_db.close()

        # Dateiname für Download generieren
        current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"mandant_{tenant_name}_{current_date}.sqlite"

        infoLog(
            MODULE_NAME,
            f"Exportiere Datenbank für Mandant {tenant_name} ({tenant_id})",
            details={"tenant_id": tenant_id, "filename": filename}
        )

        # FileResponse mit korrekten Headers zurückgeben
        return FileResponse(
            path=db_path,
            filename=filename,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        # HTTPExceptions weiterleiten
        raise
    except Exception as e:
        errorLog(
            MODULE_NAME,
            f"Unerwarteter Fehler beim Export für Mandant {tenant_id}",
            details={"tenant_id": tenant_id, "error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Exportieren der Datenbank: {str(e)}"
        )


@router.post("/import-database")
async def import_tenant_database(
    new_tenant_name: str = Form(...),
    database_file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user_id_for_import),
    main_db: Session = Depends(get_db)
):
    """
    Importiert eine SQLite-Datenbank und erstellt einen neuen Mandanten.
    """
    debugLog(
        MODULE_NAME,
        f"Import-Request für neuen Mandanten '{new_tenant_name}'",
        details={"new_tenant_name": new_tenant_name, "filename": database_file.filename}
    )

    try:
        # Validierung der hochgeladenen Datei
        if not database_file.filename.endswith('.sqlite') and not database_file.filename.endswith('.db'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nur SQLite-Dateien (.sqlite oder .db) sind erlaubt"
            )

        # Sicherstellen, dass das Tenant-DB-Verzeichnis existiert
        if not os.path.exists(TENANT_DB_DIR):
            os.makedirs(TENANT_DB_DIR)

        # Temporäre Datei für Validierung erstellen
        temp_file_path = os.path.join(TENANT_DB_DIR, f"temp_{database_file.filename}")

        try:
            # Datei temporär speichern
            with open(temp_file_path, "wb") as temp_file:
                content = await database_file.read()
                temp_file.write(content)

            # Schema-Validierung durchführen
            if not _validate_database_schema(temp_file_path):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ungültiges Datenbankschema. Die Datei enthält nicht die erwarteten Tabellen."
                )

            # Neuen Mandanten in Hauptdatenbank erstellen
            tenant_create = schemas.TenantCreate(
                name=new_tenant_name,
                user_id=current_user_id
            )

            new_tenant = crud.create_tenant(db=main_db, tenant=tenant_create)

            # Mandanten-Datenbank initialisieren
            init_tenant_db(new_tenant.uuid)

            # Importierte Datei an finalen Ort kopieren
            final_db_path = get_tenant_db_url(new_tenant.uuid).replace("sqlite:///", "")
            shutil.copy2(temp_file_path, final_db_path)

            infoLog(
                MODULE_NAME,
                f"Mandant '{new_tenant_name}' erfolgreich importiert",
                details={
                    "tenant_id": new_tenant.uuid,
                    "tenant_name": new_tenant_name,
                    "user_id": current_user_id
                }
            )

            return {
                "message": "Mandant erfolgreich importiert",
                "tenant_id": new_tenant.uuid,
                "tenant_name": new_tenant.name
            }

        finally:
            # Temporäre Datei löschen
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    except HTTPException:
        # HTTPExceptions weiterleiten
        raise
    except Exception as e:
        errorLog(
            MODULE_NAME,
            f"Unerwarteter Fehler beim Import von Mandant '{new_tenant_name}'",
            details={
                "new_tenant_name": new_tenant_name,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Importieren der Datenbank: {str(e)}"
        )


def _validate_database_schema(db_path: str) -> bool:
    """
    Validiert das Schema der SQLite-Datenbank.
    Prüft ob die erwarteten Tabellen existieren.
    """
    expected_tables = [
        "accounts",
        "account_groups",
        "categories",
        "category_groups",
        "transactions"
    ]

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Alle Tabellen in der Datenbank abrufen
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = [row[0] for row in cursor.fetchall()]

            # Prüfen ob alle erwarteten Tabellen vorhanden sind
            missing_tables = [table for table in expected_tables if table not in existing_tables]

            if missing_tables:
                warnLog(
                    MODULE_NAME,
                    f"Fehlende Tabellen in importierter Datenbank: {missing_tables}",
                    details={"missing_tables": missing_tables, "existing_tables": existing_tables}
                )
                return False

            debugLog(
                MODULE_NAME,
                "Datenbankschema-Validierung erfolgreich",
                details={"existing_tables": existing_tables}
            )
            return True

    except sqlite3.Error as e:
        errorLog(
            MODULE_NAME,
            f"Fehler bei Schema-Validierung: {str(e)}",
            details={"db_path": db_path, "error": str(e)}
        )
        return False
