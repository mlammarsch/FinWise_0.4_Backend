from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List

from ..db import crud
from ..models import schemas
from ..db.database import get_db
from ..models import user_tenant_models
from ..utils.logger import infoLog, errorLog, debugLog

MODULE_NAME = "routers.users"

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.User)
def create_user_endpoint(user: schemas.UserCreate, db: Session = Depends(get_db)):
    infoLog(MODULE_NAME, f"Attempting to create user with email: {user.email}")
    db_user_by_email = crud.get_user_by_email(db, email=user.email)
    if db_user_by_email:
        errorLog(MODULE_NAME, f"User creation failed: Email {user.email} already registered.", {"email": user.email})
        raise HTTPException(status_code=400, detail="Email already registered")

    created_user = crud.create_user(db=db, user=user)
    infoLog(MODULE_NAME, f"User created successfully with ID: {created_user.uuid}", {"user_id": created_user.uuid, "email": created_user.email})
    return created_user

@router.get("/", response_model=List[schemas.User])
def read_users_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    debugLog(MODULE_NAME, "Attempting to read users.", {"skip": skip, "limit": limit})
    try:
        users = crud.get_users(db, skip=skip, limit=limit)
        infoLog(MODULE_NAME, f"Successfully retrieved {len(users)} users.", {"count": len(users), "skip": skip, "limit": limit})
        return users
    except Exception as e:
        errorLog(MODULE_NAME, "Error retrieving users.", {"error": str(e), "skip": skip, "limit": limit})
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/{user_id}", response_model=schemas.User)
def read_user_endpoint(user_id: str, db: Session = Depends(get_db)):
    debugLog(MODULE_NAME, f"Attempting to read user with ID: {user_id}", {"user_id": user_id})
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        errorLog(MODULE_NAME, f"User with ID: {user_id} not found.", {"user_id": user_id})
        raise HTTPException(status_code=404, detail="User not found")
    infoLog(MODULE_NAME, f"Successfully retrieved user with ID: {user_id}", {"user_id": db_user.uuid})
    return db_user
