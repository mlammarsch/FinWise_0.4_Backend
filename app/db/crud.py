from sqlalchemy.orm import Session
from ..models import user_tenant_models as models
from ..models import schemas
import uuid # For generating UUIDs if not handled by DB default
import os
import sqlite3
from ..config import TENANT_DATABASE_DIR
from ..utils.logger import infoLog, errorLog, debugLog, warnLog # Importiere den neuen Logger
from .database import create_tenant_specific_tables # Importiere die neue Funktion

from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Definiere den Modulnamen für das Logging
MODULE_NAME = "db.crud"

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# User CRUD operations

def get_user(db: Session, user_id: str) -> models.User | None:
    """Retrieve a user by their UUID."""
    debugLog(MODULE_NAME, f"Attempting to get user with ID: {user_id}", {"user_id": user_id})
    user = db.query(models.User).filter(models.User.uuid == user_id).first()
    if user:
        debugLog(MODULE_NAME, f"User found with ID: {user_id}", {"user_id": user_id})
    else:
        debugLog(MODULE_NAME, f"User not found with ID: {user_id}", {"user_id": user_id})
    return user

def get_user_by_email(db: Session, email: str) -> models.User | None:
    """Retrieve a user by their email address."""
    debugLog(MODULE_NAME, f"Attempting to get user with email: {email}", {"email": email})
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        debugLog(MODULE_NAME, f"User found with email: {email}", {"email": email, "user_id": user.uuid})
    else:
        debugLog(MODULE_NAME, f"User not found with email: {email}", {"email": email})
    return user

def get_user_by_username(db: Session, username: str) -> models.User | None:
    """Retrieve a user by their username (name field)."""
    debugLog(MODULE_NAME, f"Attempting to get user with username: {username}", {"username": username})
    user = db.query(models.User).filter(models.User.name == username).first()
    if user:
        debugLog(MODULE_NAME, f"User found with username: {username}", {"username": username, "user_id": user.uuid})
    else:
        debugLog(MODULE_NAME, f"User not found with username: {username}", {"username": username})
    return user


def get_users(db: Session, skip: int = 0, limit: int = 100) -> list[models.User]:
    """Retrieve a list of users."""
    debugLog(MODULE_NAME, "Attempting to get list of users", {"skip": skip, "limit": limit})
    users = db.query(models.User).offset(skip).limit(limit).all()
    debugLog(MODULE_NAME, f"Retrieved {len(users)} users", {"count": len(users)})
    return users

def create_user_with_password(db: Session, user: schemas.RegisterUserPayload) -> models.User:
    """Create a new user with a hashed password (for registration endpoint)."""
    debugLog(MODULE_NAME, f"Attempting to create user with email: {user.email} (with password)", {"username": user.name, "email": user.email})
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_password
        # createdAt und updatedAt werden automatisch durch SQLAlchemy gesetzt
        # UUID wird automatisch durch SQLAlchemy default gesetzt
    )
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        infoLog(MODULE_NAME, f"User created successfully with ID: {db_user.uuid} (with password)", {"user_id": db_user.uuid, "email": db_user.email})
        return db_user
    except Exception as e:
        errorLog(MODULE_NAME, f"Error creating user with email: {user.email} (with password)", {"username": user.name, "email": user.email, "error": str(e)})
        db.rollback() # Wichtig: Rollback bei Fehler
        raise # Fehler weiterwerfen, damit der Aufrufer ihn behandeln kann

def create_user(db: Session, user: schemas.UserSyncPayload) -> models.User:
    """Create or update a user from frontend sync data (now with optional password hash)."""
    debugLog(MODULE_NAME, f"Attempting to create/update user from sync with UUID: {user.uuid}", {"user_id": user.uuid, "email": user.email, "has_hash": user.hashed_password is not None})
    db_user = db.query(models.User).filter(models.User.uuid == user.uuid).first()

    if db_user:
        # User exists, update data
        debugLog(MODULE_NAME, f"User with UUID {user.uuid} found during sync, updating.", {"user_id": user.uuid})
        db_user.name = user.name
        db_user.email = user.email
        if user.hashed_password is not None:
            db_user.hashed_password = user.hashed_password
            debugLog(MODULE_NAME, f"User with UUID {user.uuid} - password hash updated from sync.", {"user_id": user.uuid})
        # updatedAt wird automatisch durch SQLAlchemy onupdate gesetzt
        infoLog(MODULE_NAME, f"User with UUID {user.uuid} updated from sync.", {"user_id": user.uuid})
    else:
        # User does not exist, create new one with provided UUID
        debugLog(MODULE_NAME, f"User with UUID {user.uuid} not found during sync, creating new.", {"user_id": user.uuid})
        db_user = models.User(
            uuid=user.uuid, # Use UUID from frontend
            name=user.name,
            email=user.email,
            hashed_password=user.hashed_password # Set password hash if provided
            # createdAt und updatedAt werden automatisch gesetzt
        )
        db.add(db_user)
        infoLog(MODULE_NAME, f"New user with UUID {user.uuid} created from sync.", {"user_id": user.uuid, "hash_provided": user.hashed_password is not None})

    try:
        db.commit()
        db.refresh(db_user)
        infoLog(MODULE_NAME, f"User sync operation successful for UUID: {db_user.uuid}", {"user_id": db_user.uuid})
        return db_user
    except Exception as e:
        errorLog(MODULE_NAME, f"Error during user sync operation for UUID: {user.uuid}", {"user_id": user.uuid, "error": str(e)})
        db.rollback()
        raise

def update_user(db: Session, user_id: str, user_data: schemas.UserBase) -> models.User | None:
    """Update user data (name, email) for an existing user."""
    debugLog(MODULE_NAME, f"Attempting to update user with ID: {user_id}", {"user_id": user_id, "user_data": user_data.model_dump_json()})
    db_user = db.query(models.User).filter(models.User.uuid == user_id).first()
    if db_user:
        try:
            db_user.name = user_data.name
            db_user.email = user_data.email
            # updatedAt wird automatisch durch SQLAlchemy onupdate gesetzt
            db.commit()
            db.refresh(db_user)
            infoLog(MODULE_NAME, f"User with ID: {user_id} updated successfully.", {"user_id": user_id})
            return db_user
        except Exception as e:
            errorLog(MODULE_NAME, f"Error updating user with ID: {user_id}", {"user_id": user_id, "error": str(e)})
            db.rollback()
            raise
    else:
        warnLog(MODULE_NAME, f"User with ID: {user_id} not found for update.", {"user_id": user_id})
        return None

def authenticate_user(db: Session, username_or_email: str, password: str) -> models.User | None:
    """Authenticate a user by username or email and password."""
    debugLog(MODULE_NAME, f"Attempting to authenticate user: {username_or_email}")
    user = get_user_by_email(db, email=username_or_email)
    if not user:
        user = get_user_by_username(db, username=username_or_email)

    if not user or not user.hashed_password:
        warnLog(MODULE_NAME, f"Authentication failed: User not found or no password set for {username_or_email}")
        return None

    if not verify_password(password, user.hashed_password):
        warnLog(MODULE_NAME, f"Authentication failed: Incorrect password for user {user.uuid}", {"user_id": user.uuid})
        return None

    infoLog(MODULE_NAME, f"Authentication successful for user {user.uuid}", {"user_id": user.uuid})
    return user

# Tenant CRUD operations
def get_tenant(db: Session, tenant_id: str) -> models.Tenant | None:
    return db.query(models.Tenant).filter(models.Tenant.uuid == tenant_id).first()

def get_tenant_by_name_and_user_id(db: Session, name: str, user_id: str) -> models.Tenant | None:
    return db.query(models.Tenant).filter(models.Tenant.name == name, models.Tenant.user_id == user_id).first()

def get_tenants_by_user(db: Session, user_id: str, skip: int = 0, limit: int = 100) -> list[models.Tenant]:
    return db.query(models.Tenant).filter(models.Tenant.user_id == user_id).offset(skip).limit(limit).all()

def get_tenants(db: Session, skip: int = 0, limit: int = 100) -> list[models.Tenant]:
    return db.query(models.Tenant).offset(skip).limit(limit).all()

def create_tenant(db: Session, tenant: schemas.TenantCreate) -> models.Tenant:
    debugLog(MODULE_NAME, f"Attempting to create tenant '{tenant.name}' for user ID: {tenant.user_id}", {"tenant_name": tenant.name, "user_id": tenant.user_id})
    # Verwende die vom Frontend gesendete UUID, falls vorhanden, sonst lass die DB eine generieren.
    # Da wir im Frontend immer eine UUID generieren, sollte tenant.uuid hier immer gesetzt sein.
    db_tenant = models.Tenant(
        uuid=tenant.uuid, # Verwende die übergebene UUID
        name=tenant.name,
        user_id=tenant.user_id
    )
    try:
        db.add(db_tenant)
        db.commit()
        db.refresh(db_tenant)
        infoLog(MODULE_NAME, f"Tenant '{db_tenant.name}' (ID: {db_tenant.uuid}) created in main DB for user ID: {db_tenant.user_id}.", {"tenant_id": db_tenant.uuid, "tenant_name": db_tenant.name, "user_id": db_tenant.user_id})
    except Exception as e:
        errorLog(MODULE_NAME, f"Error creating tenant '{tenant.name}' in main DB for user ID: {tenant.user_id}", {"error": str(e)})
        db.rollback()
        raise

    try:
        if not os.path.exists(TENANT_DATABASE_DIR):
            os.makedirs(TENANT_DATABASE_DIR)
            infoLog(MODULE_NAME, f"Created tenant database directory: {TENANT_DATABASE_DIR}")

        tenant_db_filename = f"finwiseTenantDB_{db_tenant.uuid}.db"
        tenant_db_path = os.path.join(TENANT_DATABASE_DIR, tenant_db_filename)

        if not os.path.exists(tenant_db_path):
            conn = sqlite3.connect(tenant_db_path)
            conn.close()
            infoLog(MODULE_NAME, f"Created tenant-specific database file: {tenant_db_path}", {"tenant_id": db_tenant.uuid})

            # === NEU: Tabellen in der Mandanten-DB erstellen ===
            create_tenant_specific_tables(db_tenant.uuid)
            # =====================================================
        else:
            warnLog(MODULE_NAME, f"Tenant-specific database file already exists: {tenant_db_path}. Attempting to ensure tables exist.", {"tenant_id": db_tenant.uuid})
            # Auch wenn die Datei existiert, könnten die Tabellen fehlen (z.B. durch einen vorherigen Fehler)
            # Daher rufen wir create_tenant_specific_tables trotzdem auf.
            # Die Funktion create_all ist idempotent und erstellt Tabellen nur, wenn sie nicht existieren.
            create_tenant_specific_tables(db_tenant.uuid)

        return db_tenant # Tenant-Objekt erst nach erfolgreicher DB-Erstellung und Tabellenerstellung zurückgeben

    except Exception as e:
        # Hier fangen wir Fehler sowohl von der Dateierstellung als auch von der Tabellenerstellung ab.
        errorLog(MODULE_NAME, f"Failed during tenant-specific database setup (file or tables) for tenant {db_tenant.uuid}: {str(e)}", {"tenant_id": db_tenant.uuid})
        # WICHTIG: Da der Tenant bereits in der Haupt-DB commited wurde, hier aber die Datei-Erstellung fehlschlägt,
        # wäre ein Rollback des Haupt-DB-Eintrags ideal, aber komplexer (erfordert z.B. SAGA-Pattern oder Zwei-Phasen-Commit-Logik).
        # Für den Moment: Fehler loggen und Exception weiterwerfen. Der Aufrufer (Router) muss entscheiden, wie er damit umgeht.
        # Der Router könnte dann versuchen, den Tenant aus der Haupt-DB zu löschen.
        raise # Fehler weiterwerfen, damit der Router ihn behandeln kann (z.B. HTTP 500)

def delete_tenant(db: Session, tenant_id: str) -> models.Tenant | None:
    debugLog(MODULE_NAME, f"Attempting to delete tenant with ID: {tenant_id}", {"tenant_id": tenant_id})
    db_tenant = db.query(models.Tenant).filter(models.Tenant.uuid == tenant_id).first()
    if db_tenant:
        try:
            db.delete(db_tenant)
            db.commit()
            infoLog(MODULE_NAME, f"Tenant with ID: {tenant_id} deleted from main DB.", {"tenant_id": tenant_id})
            # Das Löschen der physischen DB-Datei ist hier nicht implementiert,
            # könnte aber als nächster Schritt im Router oder hier erfolgen.
            return db_tenant # Rückgabe des gelöschten Objekts (vor dem Commit war es noch in der Session)
        except Exception as e:
            errorLog(MODULE_NAME, f"Error deleting tenant with ID: {tenant_id} from main DB.", {"tenant_id": tenant_id, "error": str(e)})
            db.rollback()
            raise
    else:
        warnLog(MODULE_NAME, f"Tenant with ID: {tenant_id} not found for deletion.", {"tenant_id": tenant_id})
        return None
