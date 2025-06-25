import uuid
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import JSONResponse, FileResponse
from starlette import status

from app.services.file_service import FileService
from app.api import deps
from app.models import user_tenant_models as models # User model for current_user dependency

router = APIRouter()
file_service = FileService()

ALLOWED_MIME_TYPES = ["image/png", "image/jpeg"]
MIME_TYPE_TO_EXTENSION = {
    "image/png": "png",
    "image/jpeg": "jpg",
}

@router.post("/upload", response_model=dict)
async def upload_image(
    file: UploadFile = File(...),
    tenant_id: str = Depends(deps.get_current_tenant_id)
):
    """
    Uploads a logo for a given entity (account or account_group).
    Validates file type (PNG/JPG) and saves the file with a unique name
    under the tenant's directory.
    """
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


    unique_filename = f"{uuid.uuid4()}.{original_extension}"

    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Lesen der Datei: {str(e)}"
        )

    saved_relative_path = file_service.save_logo(
        filename=unique_filename,
        file_content=file_bytes,
        tenant_id=tenant_id
    )

    if not saved_relative_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logo konnte nicht gespeichert werden."
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"image_url": saved_relative_path}
    )

@router.delete("/images/{image_url:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image_endpoint(
    image_url: str,
    current_tenant_id: str = Depends(deps.get_current_tenant_id)
):
    """
    Deletes a logo file specified by its relative path.
    The path should include the tenant_id (e.g., "tenant_id/filename.ext").
    Ensures the user can only delete logos belonging to their current tenant.
    """
    if "/" not in image_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image URL format. Expected 'tenant_id/filename.ext'.")

    tenant_id_from_path = image_url.split("/", 1)[0]

    if tenant_id_from_path != current_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Access to this resource is denied."
        )

    success = file_service.delete_image(relative_image_url=image_url)

    if not success:
        # FileService.delete_logo logs the specific error (e.g., file not found)
        # We return a generic 404 if deletion wasn't successful for any reason on the service side.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Logo nicht gefunden oder konnte nicht gelöscht werden."
        )

    # For a DELETE operation, returning HTTP 204 No Content is standard practice.
    # No need to return a body.
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/images/{image_url:path}")
async def get_image(
    image_url: str,
    current_tenant_id: str = Depends(deps.get_current_tenant_id)
):
    """
    Retrieves a logo file specified by its relative path.
    The path should include the tenant_id (e.g., "tenant_id/filename.ext").
    Ensures the user can only access logos belonging to their current tenant.
    Returns the logo as a FileResponse with the correct MIME type.
    """
    if "/" not in image_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image URL format. Expected 'tenant_id/filename.ext'.")

    tenant_id_from_path = image_url.split("/", 1)[0]

    if tenant_id_from_path != current_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Access to this resource is denied."
        )

    absolute_image_path = file_service.get_image_path(relative_image_url=image_url)

    if absolute_image_path is None or not os.path.exists(absolute_image_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    _, extension = os.path.splitext(image_url)
    extension = extension.lower()

    media_type: Optional[str] = None
    if extension == ".png":
        media_type = "image/png"
    elif extension in [".jpg", ".jpeg"]:
        media_type = "image/jpeg"
    else:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported media type")

    return FileResponse(path=absolute_logo_path, media_type=media_type)
