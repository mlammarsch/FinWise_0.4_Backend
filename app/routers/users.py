from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Annotated

from ..db import crud
from ..models import schemas
from ..db.database import get_db
from ..models import user_tenant_models
from ..utils.logger import infoLog, errorLog, debugLog

MODULE_NAME = "routers.users"

router = APIRouter(
    tags=["users"],
    responses={404: {"description": "Not found"}},
)

@router.post("/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
def register_user_endpoint(user: schemas.RegisterUserPayload, db: Session = Depends(get_db)):
    db_user_by_email = crud.get_user_by_email(db, email=user.email)
    if db_user_by_email:
        errorLog(MODULE_NAME, f"User registration failed: Email {user.email} already registered.", {"email": user.email})
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user_by_username = crud.get_user_by_username(db, username=user.name)
    if db_user_by_username:
         errorLog(MODULE_NAME, f"User registration failed: Username {user.name} already taken.", {"username": user.name})
         raise HTTPException(status_code=400, detail="Username already taken")

    created_user = crud.create_user_with_password(db=db, user=user)
    infoLog(MODULE_NAME, f"User registered successfully with ID: {created_user.uuid}", {"user_id": created_user.uuid, "email": created_user.email})
    return created_user

@router.post("/login", response_model=schemas.User)
def login_user_endpoint(credentials: schemas.LoginPayload, db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, username_or_email=credentials.username_or_email, password=credentials.password)
    if not user:
        errorLog(MODULE_NAME, f"Login failed: Invalid credentials for {credentials.username_or_email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    infoLog(MODULE_NAME, f"User {user.uuid} logged in successfully.", {"user_id": user.uuid})
    return user

@router.post("/users", response_model=schemas.User)
def sync_create_user_endpoint(user_data: schemas.UserSyncPayload, db: Session = Depends(get_db)):
    """Endpoint to sync user data (create or update) from the frontend using UUID."""
    infoLog(MODULE_NAME, f"Attempting to sync/create user from frontend with UUID: {user_data.uuid}, hash provided: {user_data.hashed_password is not None}")
    synced_user = crud.create_user(db=db, user=user_data)
    infoLog(MODULE_NAME, f"User sync/create successful for UUID: {synced_user.uuid}", {"user_id": synced_user.uuid})
    return synced_user

@router.put("/users/{user_id}", response_model=schemas.User)
def sync_update_user_endpoint(user_id: str, user_data: schemas.UserBase, db: Session = Depends(get_db)):
    """Endpoint to sync user updates (name, email) from the frontend for an existing user."""
    infoLog(MODULE_NAME, f"Attempting to sync/update user with ID: {user_id} from frontend.")
    db_user = crud.update_user(db=db, user_id=user_id, user_data=user_data)
    if db_user is None:
        errorLog(MODULE_NAME, f"User with ID: {user_id} not found for sync update.", {"user_id": user_id})
        raise HTTPException(status_code=404, detail="User not found")
    infoLog(MODULE_NAME, f"User sync/update successful for ID: {db_user.uuid}", {"user_id": db_user.uuid})
    return db_user

@router.get("/users", response_model=List[schemas.User])
def read_users_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Retrieves a list of users from the database."""
    debugLog(MODULE_NAME, "Attempting to read users.", {"skip": skip, "limit": limit})
    try:
        users = crud.get_users(db, skip=skip, limit=limit)
        infoLog(MODULE_NAME, f"Successfully retrieved {len(users)} users.", {"count": len(users), "skip": skip, "limit": limit})
        return users
    except Exception as e:
        errorLog(MODULE_NAME, "Error retrieving users.", {"error": str(e), "skip": skip, "limit": limit})
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/users/{user_id}", response_model=schemas.User)
def read_user_endpoint(user_id: str, db: Session = Depends(get_db)):
    debugLog(MODULE_NAME, f"Attempting to read user with ID: {user_id}", {"user_id": user_id})
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        errorLog(MODULE_NAME, f"User with ID: {user_id} not found.", {"user_id": user_id})
        raise HTTPException(status_code=404, detail="User not found")
    infoLog(MODULE_NAME, f"Successfully retrieved user with ID: {db_user.uuid}", {"user_id": db_user.uuid})
    return db_user
