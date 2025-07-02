import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from app.db.session import get_db
from app.utils.logger import debugLog, infoLog, errorLog
from app.services.auth import get_current_user
from sqlalchemy.orm import Session
from app.models.user_tenant_models import User, Tenant

router = APIRouter()

UPLOAD_DIR = "uploads"

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Holen des tenant_id aus dem aktuellen User
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        errorLog("ImageUpload", "Tenant nicht gefunden für Benutzer", {"user_id": current_user.id})
        raise HTTPException(status_code=404, detail="Tenant nicht gefunden")

    tenant_id = tenant.id
    tenant_upload_dir = os.path.join(UPLOAD_DIR, f"tenant_{tenant_id}", "images")

    # Erstellen des Verzeichnisses, falls nicht vorhanden
    os.makedirs(tenant_upload_dir, exist_ok=True)

    # Generieren eines eindeutigen Dateinamens
    file_ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(tenant_upload_dir, filename)

    try:
        # Speichern der Datei
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        infoLog("ImageUpload", "Bild erfolgreich hochgeladen", {
            "tenant_id": tenant_id,
            "file_path": file_path,
            "original_filename": file.filename
        })

        return JSONResponse(content={"logo_path": file_path}, status_code=200)

    except Exception as e:
        errorLog("ImageUpload", "Fehler beim Hochladen des Bildes", {
            "tenant_id": tenant_id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Fehler beim Hochladen des Bildes")
