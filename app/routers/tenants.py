from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..db import crud
from ..models import schemas
from ..db.database import get_db
from ..services.tenant_service import TenantService
from ..utils.logger import infoLog, errorLog, debugLog

MODULE_NAME = "routers.tenants"

router = APIRouter(
    prefix="/tenants",
    tags=["tenants"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.Tenant)
def create_tenant_endpoint(tenant: schemas.TenantCreate, db: Session = Depends(get_db)):
    infoLog(MODULE_NAME, f"Attempting to create tenant '{tenant.name}' for user ID: {tenant.user_id}", {"tenant_name": tenant.name, "user_id": tenant.user_id})
    user = crud.get_user(db, user_id=tenant.user_id)
    if not user:
        errorLog(MODULE_NAME, f"User with ID {tenant.user_id} not found during tenant creation.", {"user_id": tenant.user_id, "tenant_name": tenant.name})
        raise HTTPException(status_code=404, detail=f"User with id {user_id} not found")

    existing_tenant = crud.get_tenant_by_name_and_user_id(db, name=tenant.name, user_id=tenant.user_id)
    if existing_tenant:
        errorLog(MODULE_NAME, f"Tenant with name '{tenant.name}' already exists for user ID {tenant.user_id}.", {"tenant_name": tenant.name, "user_id": tenant.user_id})
        raise HTTPException(status_code=400, detail=f"Tenant with name '{tenant.name}' already exists for this user.")

    try:
        new_tenant = crud.create_tenant(db=db, tenant=tenant)
        infoLog(MODULE_NAME, f"Tenant '{new_tenant.name}' (ID: {new_tenant.uuid}) created successfully for user ID: {new_tenant.user_id}.", {"tenant_id": new_tenant.uuid, "tenant_name": new_tenant.name, "user_id": new_tenant.user_id})
        return new_tenant
    except Exception as e:
        errorLog(MODULE_NAME, f"Error during tenant creation for user ID {tenant.user_id}.", {"tenant_name": tenant.name, "user_id": tenant.user_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during tenant creation: {str(e)}")


@router.get("/", response_model=List[schemas.Tenant])
def read_tenants_endpoint(
    user_id: Optional[str] = Query(None, description="Filter tenants by user ID"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    debugLog(MODULE_NAME, "Attempting to read tenants.", {"user_id": user_id, "skip": skip, "limit": limit})
    try:
        if user_id:
            user = crud.get_user(db, user_id=user_id)
            if not user:
                errorLog(MODULE_NAME, f"User with ID {user_id} not found when trying to read tenants.", {"user_id": user_id})
                raise HTTPException(status_code=404, detail=f"User with id {user_id} not found")
            tenants = crud.get_tenants_by_user(db, user_id=user_id, skip=skip, limit=limit)
            infoLog(MODULE_NAME, f"Successfully retrieved {len(tenants)} tenants for user ID {user_id}.", {"count": len(tenants), "user_id": user_id})
        else:
            tenants = crud.get_tenants(db, skip=skip, limit=limit)
            infoLog(MODULE_NAME, f"Successfully retrieved {len(tenants)} tenants (all users).", {"count": len(tenants)})
        return tenants
    except Exception as e:
        errorLog(MODULE_NAME, "Error retrieving tenants.", {"error": str(e), "user_id": user_id, "skip": skip, "limit": limit})
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/{tenant_id}", response_model=schemas.Tenant)
def read_tenant_endpoint(tenant_id: str, db: Session = Depends(get_db)):
    debugLog(MODULE_NAME, f"Attempting to read tenant with ID: {tenant_id}", {"tenant_id": tenant_id})
    db_tenant = crud.get_tenant(db, tenant_id=tenant_id)
    if db_tenant is None:
        errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found.", {"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    infoLog(MODULE_NAME, f"Successfully retrieved tenant with ID: {tenant_id}", {"tenant_id": db_tenant.uuid})
    return db_tenant


@router.put("/{tenant_id}", response_model=schemas.Tenant)
def update_tenant_endpoint(
    tenant_id: str,
    tenant_update: schemas.TenantUpdate,
    user_id: str = Query(..., description="User ID for authorization"),
    db: Session = Depends(get_db)
):
    """
    Aktualisiert einen Mandanten (z.B. Name ändern).
    Validierung: Nur Owner kann Mandant bearbeiten.
    """
    infoLog(MODULE_NAME, f"Attempting to update tenant with ID: {tenant_id}",
           {"tenant_id": tenant_id, "user_id": user_id, "new_name": tenant_update.name})

    # Mandant prüfen
    db_tenant = crud.get_tenant(db, tenant_id=tenant_id)
    if db_tenant is None:
        errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found for update.",
                {"tenant_id": tenant_id, "user_id": user_id})
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Berechtigung prüfen
    if db_tenant.user_id != user_id:
        errorLog(MODULE_NAME, f"User {user_id} not authorized to update tenant {tenant_id}",
                {"tenant_id": tenant_id, "user_id": user_id, "owner_id": db_tenant.user_id})
        raise HTTPException(status_code=403, detail=f"User {user_id} is not authorized to update tenant {tenant_id}")

    # Name-Duplikat prüfen (falls Name geändert wird)
    if tenant_update.name != db_tenant.name:
        existing_tenant = crud.get_tenant_by_name_and_user_id(db, name=tenant_update.name, user_id=user_id)
        if existing_tenant and existing_tenant.uuid != tenant_id:
            errorLog(MODULE_NAME, f"Tenant with name '{tenant_update.name}' already exists for user {user_id}",
                    {"tenant_name": tenant_update.name, "user_id": user_id, "existing_tenant_id": existing_tenant.uuid})
            raise HTTPException(status_code=400, detail=f"Tenant with name '{tenant_update.name}' already exists for this user.")

    try:
        updated_tenant = crud.update_tenant(db=db, tenant_id=tenant_id, tenant_update=tenant_update)
        if updated_tenant is None:
            errorLog(MODULE_NAME, f"Failed to update tenant with ID: {tenant_id}",
                    {"tenant_id": tenant_id, "user_id": user_id})
            raise HTTPException(status_code=500, detail="Failed to update tenant")

        infoLog(MODULE_NAME, f"Tenant with ID: {tenant_id} successfully updated",
               {"tenant_id": tenant_id, "old_name": db_tenant.name, "new_name": updated_tenant.name})
        return updated_tenant

    except Exception as e:
        errorLog(MODULE_NAME, f"Error updating tenant {tenant_id}: {str(e)}",
                {"tenant_id": tenant_id, "user_id": user_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during tenant update: {str(e)}")


@router.delete("/{tenant_id}", response_model=schemas.Tenant)
def delete_tenant_endpoint(tenant_id: str, db: Session = Depends(get_db)):
    infoLog(MODULE_NAME, f"Attempting to delete tenant with ID: {tenant_id}", {"tenant_id": tenant_id})
    db_tenant = crud.get_tenant(db, tenant_id=tenant_id)
    if db_tenant is None:
        errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found for deletion.", {"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")

    deleted_tenant_data = crud.delete_tenant(db, tenant_id=tenant_id)

    if deleted_tenant_data is None:
        errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} could not be deleted or was already deleted.", {"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found or could not be deleted")

    infoLog(MODULE_NAME, f"Tenant with ID: {tenant_id} successfully marked for deletion in main DB.", {"tenant_id": tenant_id})
    return deleted_tenant_data


@router.delete("/{tenant_id}/complete", response_model=schemas.Tenant)
async def delete_tenant_completely_endpoint(
    tenant_id: str,
    user_id: str = Query(..., description="User ID for authorization"),
    db: Session = Depends(get_db)
):
    """
    Löscht einen Mandanten vollständig:
    - Löscht Mandanten-Eintrag aus Haupt-DB
    - Löscht entsprechende SQLite-Datei aus tenant_databases/
    - Validierung: Nur Owner kann Mandant löschen
    - Sendet WebSocket-Benachrichtigungen an andere Clients
    """
    infoLog(MODULE_NAME, f"Attempting complete tenant deletion for ID: {tenant_id}",
           {"tenant_id": tenant_id, "user_id": user_id})

    try:
        deleted_tenant = await TenantService.delete_tenant_completely(db, tenant_id, user_id)

        if deleted_tenant is None:
            errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found for complete deletion",
                    {"tenant_id": tenant_id, "user_id": user_id})
            raise HTTPException(status_code=404, detail="Tenant not found")

        infoLog(MODULE_NAME, f"Tenant with ID: {tenant_id} completely deleted successfully",
               {"tenant_id": tenant_id, "tenant_name": deleted_tenant.name})
        return deleted_tenant

    except PermissionError as e:
        errorLog(MODULE_NAME, f"Permission denied for complete tenant deletion: {str(e)}",
                {"tenant_id": tenant_id, "user_id": user_id})
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        # Re-raise HTTP exceptions (like 404) without modification
        raise
    except Exception as e:
        # Check if the error message indicates a "not found" scenario
        error_str = str(e).lower()
        if "not found" in error_str or "404" in error_str:
            errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found during deletion: {str(e)}",
                    {"tenant_id": tenant_id, "user_id": user_id})
            raise HTTPException(status_code=404, detail="Tenant not found")
        else:
            errorLog(MODULE_NAME, f"Error during complete tenant deletion for {tenant_id}: {str(e)}",
                    {"tenant_id": tenant_id, "user_id": user_id, "error": str(e)})
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred during complete tenant deletion: {str(e)}")


@router.post("/{tenant_id}/reset-database")
async def reset_tenant_database_endpoint(
    tenant_id: str,
    user_id: str = Query(..., description="User ID for authorization"),
    db: Session = Depends(get_db)
):
    """
    Setzt die Mandanten-Datenbank zurück:
    - Löscht alle Inhalte aller Tabellen in der Mandanten-DB
    - Führt Initial-Setup durch (wie bei Mandanten-Erstellung)
    - Behält Mandanten-Eintrag in Haupt-DB bei
    - Validierung: Nur Owner kann DB zurücksetzen
    """
    infoLog(MODULE_NAME, f"Attempting tenant database reset for ID: {tenant_id}",
           {"tenant_id": tenant_id, "user_id": user_id})

    try:
        reset_successful = await TenantService.reset_tenant_database(db, tenant_id, user_id)

        if not reset_successful:
            errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found for database reset",
                    {"tenant_id": tenant_id, "user_id": user_id})
            raise HTTPException(status_code=404, detail="Tenant not found")

        infoLog(MODULE_NAME, f"Tenant database successfully reset for ID: {tenant_id}",
               {"tenant_id": tenant_id, "user_id": user_id})
        return {"message": f"Database for tenant {tenant_id} has been successfully reset", "tenant_id": tenant_id}

    except PermissionError as e:
        errorLog(MODULE_NAME, f"Permission denied for tenant database reset: {str(e)}",
                {"tenant_id": tenant_id, "user_id": user_id})
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        errorLog(MODULE_NAME, f"Error during tenant database reset for {tenant_id}: {str(e)}",
                {"tenant_id": tenant_id, "user_id": user_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during database reset: {str(e)}")


@router.delete("/{tenant_id}/sync-queue")
async def clear_sync_queue_endpoint(
    tenant_id: str,
    user_id: str = Query(..., description="User ID for authorization (debugging/maintenance only)"),
    db: Session = Depends(get_db)
):
    """
    Löscht alle SyncQueue-Einträge für den Mandanten.
    Nur für Debugging/Wartung gedacht.

    WARNUNG: Diese Operation kann zu Datenverlust führen, wenn noch nicht
    synchronisierte Änderungen in der Queue stehen!
    """
    infoLog(MODULE_NAME, f"Attempting to clear sync queue for tenant: {tenant_id}",
           {"tenant_id": tenant_id, "user_id": user_id})

    # Validierung: Mandant muss existieren
    db_tenant = crud.get_tenant(db, tenant_id=tenant_id)
    if not db_tenant:
        errorLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found for sync queue clearing",
                {"tenant_id": tenant_id, "user_id": user_id})
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Berechtigung prüfen
    if db_tenant.user_id != user_id:
        errorLog(MODULE_NAME, f"User {user_id} not authorized to clear sync queue for tenant {tenant_id}",
                {"tenant_id": tenant_id, "user_id": user_id, "owner_id": db_tenant.user_id})
        raise HTTPException(status_code=403, detail=f"User {user_id} is not authorized to clear sync queue for tenant {tenant_id}")

    try:
        clear_successful = await TenantService.clear_sync_queue(tenant_id, user_id)

        if clear_successful:
            infoLog(MODULE_NAME, f"Sync queue successfully cleared for tenant: {tenant_id}",
                   {"tenant_id": tenant_id, "user_id": user_id})
            return {"message": f"Sync queue for tenant {tenant_id} has been successfully cleared", "tenant_id": tenant_id}
        else:
            errorLog(MODULE_NAME, f"Failed to clear sync queue for tenant: {tenant_id}",
                    {"tenant_id": tenant_id, "user_id": user_id})
            raise HTTPException(status_code=500, detail="Failed to clear sync queue")

    except Exception as e:
        errorLog(MODULE_NAME, f"Error clearing sync queue for tenant {tenant_id}: {str(e)}",
                {"tenant_id": tenant_id, "user_id": user_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while clearing sync queue: {str(e)}")
