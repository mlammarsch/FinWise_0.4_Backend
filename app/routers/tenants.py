from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..db import crud
from ..models import schemas
from ..db.database import get_db
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
