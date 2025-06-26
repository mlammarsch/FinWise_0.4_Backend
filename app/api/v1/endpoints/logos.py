import uuid
import os
from typing import Optional
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import JSONResponse, FileResponse
from starlette import status
from PIL import Image
from sqlalchemy.orm import Session

from app.services.file_service import FileService
from app.api import deps
from app.models import user_tenant_models as models # User model for current_user dependency
from app.models.financial_models import Account, AccountGroup
from app.utils.logger import errorLog, infoLog, debugLog

router = APIRouter()
file_service = FileService()

ALLOWED_MIME_TYPES = ["image/png", "image/jpeg"]
MIME_TYPE_TO_EXTENSION = {
    "image/png": "png",
    "image/jpeg": "jpg",
}

@router.post("/upload", response_model=dict)
async def upload_logo(
    file: UploadFile = File(...),
    entity_id: str = Form(...),
    entity_type: str = Form(...),
    tenant_id: str = Form(...)
):
    """
    Uploads a logo for a given entity (account or account_group).
    Validates file type (PNG/JPG) and saves the file with a unique name
    under the tenant's directory.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID is required."
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Dateityp. Erlaubt sind: {', '.join(ALLOWED_MIME_TYPES)}. Erhalten: {file.content_type}"
        )

    original_extension = MIME_TYPE_TO_EXTENSION.get(file.content_type)
    if not original_extension:
        # Fallback, sollte durch obige Prüfung eigentlich nicht erreicht werden
        _, original_extension_from_filename = os.path.splitext(file.filename)
        original_extension = original_extension_from_filename.lstrip('.')
        if not original_extension or original_extension.lower() not in ['png', 'jpg', 'jpeg']:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Konnte Dateiendung nicht bestimmen oder ungültige Endung."
            )
        if original_extension == "jpeg": # normalize to jpg
            original_extension = "jpg"


    # Eindeutiger Dateiname mit PNG-Endung (da wir immer als PNG speichern)
    unique_filename = f"{uuid.uuid4()}.png"

    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Lesen der Datei: {str(e)}"
        )

    # Bildskalierung mit Pillow auf 128x128px und Konvertierung zu PNG
    try:
        # Bild aus Bytes laden
        image = Image.open(BytesIO(file_bytes))

        # Auf 128x128px skalieren mit hochwertiger Resampling-Methode
        # LANCZOS bietet die beste Qualität für Verkleinerungen
        resized_image = image.resize((128, 128), Image.Resampling.LANCZOS)

        # Zu RGB konvertieren falls nötig (für PNG-Kompatibilität)
        if resized_image.mode in ('RGBA', 'LA', 'P'):
            # Für Bilder mit Transparenz: RGBA beibehalten
            if resized_image.mode == 'P':
                resized_image = resized_image.convert('RGBA')
        elif resized_image.mode != 'RGB':
            resized_image = resized_image.convert('RGB')

        # Bild als PNG in BytesIO speichern
        output_buffer = BytesIO()
        resized_image.save(output_buffer, format='PNG', optimize=True)
        processed_file_bytes = output_buffer.getvalue()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Verarbeiten des Bildes: {str(e)}"
        )

    saved_relative_path = file_service.save_logo(
        filename=unique_filename,
        file_content=processed_file_bytes,
        tenant_id=tenant_id
    )

    if not saved_relative_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logo konnte nicht gespeichert werden."
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"logo_path": saved_relative_path, "entity_id": entity_id, "entity_type": entity_type}
    )

@router.delete("/{logo_path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_logo_endpoint(
    logo_path: str,
    current_tenant_id: str = Depends(deps.get_current_tenant_id),
    db: Session = Depends(deps.get_tenant_db_session)
):
    """
    Deletes a logo file specified by its relative path.
    The path should include the tenant_id (e.g., "tenant_id/filename.ext").
    Ensures the user can only delete logos belonging to their current tenant.
    Performs reference check to ensure no entities are still using this logo.
    """
    if "/" not in logo_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid logo path format. Expected 'tenant_id/filename.ext'.")

    tenant_id_from_path = logo_path.split("/", 1)[0]

    if tenant_id_from_path != current_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Access to this resource is denied."
        )

    debugLog("LogoAPI", f"Prüfe Referenzen für Logo-Pfad: {logo_path}")

    # Prüfe, ob noch Entitäten auf dieses Logo verweisen
    try:
        # Prüfe Accounts mit logo_path
        accounts_with_logo = db.query(Account).filter(Account.logo_path == logo_path).all()
        if accounts_with_logo:
            account_names = [acc.name for acc in accounts_with_logo]
            errorLog("LogoAPI", f"Logo kann nicht gelöscht werden - wird von Accounts verwendet: {account_names}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Logo kann nicht gelöscht werden. Es wird noch von folgenden Accounts verwendet: {', '.join(account_names)}"
            )

        # Prüfe AccountGroups mit logo_path
        account_groups_with_logo = db.query(AccountGroup).filter(AccountGroup.logo_path == logo_path).all()
        if account_groups_with_logo:
            group_names = [grp.name for grp in account_groups_with_logo]
            errorLog("LogoAPI", f"Logo kann nicht gelöscht werden - wird von AccountGroups verwendet: {group_names}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Logo kann nicht gelöscht werden. Es wird noch von folgenden Account-Gruppen verwendet: {', '.join(group_names)}"
            )


        infoLog("LogoAPI", f"Keine Referenzen gefunden für Logo: {logo_path}. Löschung wird fortgesetzt.")

    except HTTPException:
        # Re-raise HTTPExceptions (unsere eigenen Fehler)
        raise
    except Exception as e:
        errorLog("LogoAPI", f"Fehler bei der Referenzprüfung für Logo {logo_path}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Überprüfung der Logo-Referenzen."
        )

    # Wenn keine Referenzen gefunden wurden, kann das Logo sicher gelöscht werden
    success = file_service.delete_logo(relative_logo_path=logo_path)

    if not success:
        # FileService.delete_logo logs the specific error (e.g., file not found)
        # We return a generic 404 if deletion wasn't successful for any reason on the service side.
        errorLog("LogoAPI", f"Logo-Datei konnte nicht gelöscht werden: {logo_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Logo nicht gefunden oder konnte nicht gelöscht werden."
        )

    infoLog("LogoAPI", f"Logo erfolgreich gelöscht: {logo_path}")
    # For a DELETE operation, returning HTTP 204 No Content is standard practice.
    # No need to return a body.
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/{logo_path:path}")
async def get_logo(
    logo_path: str
):
    """
    Retrieves a logo file specified by its relative path.
    The path should include the tenant_id (e.g., "tenant_id/filename.ext").
    Security is ensured by validating the tenant_id is part of the path structure.
    Returns the logo as a FileResponse with the correct MIME type.
    """
    debugLog("LogoAPI", f"Received request for logo_path: {logo_path}")

    if "/" not in logo_path:
        errorLog("LogoAPI", f"Invalid logo path format received: {logo_path}. Missing '/'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid logo path format. Expected 'tenant_id/filename.ext'.")

    tenant_id_from_path = logo_path.split("/", 1)[0]

    # Validate tenant_id format (basic UUID validation)
    if not tenant_id_from_path or len(tenant_id_from_path) < 32:
        errorLog("LogoAPI", f"Invalid tenant ID format in logo path: {tenant_id_from_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format in logo path."
        )

    absolute_logo_path = file_service.get_logo_path(relative_logo_path=logo_path)

    if absolute_logo_path is None or not os.path.exists(absolute_logo_path):
        errorLog("LogoAPI", f"Logo file not found or path invalid: {absolute_logo_path} for requested path {logo_path}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo not found")

    _, extension = os.path.splitext(logo_path)
    extension = extension.lower()

    media_type: str
    if extension == ".png":
        media_type = "image/png"
    elif extension in [".jpg", ".jpeg"]:
        media_type = "image/jpeg"
    else:
        errorLog("LogoAPI", f"Unknown file extension for logo: {extension}. Defaulting to application/octet-stream.")
        media_type = "application/octet-stream" # Generic binary file type

    return FileResponse(absolute_logo_path, media_type=media_type)
