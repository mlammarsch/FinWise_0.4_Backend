import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.user_tenant_models import UserSettings
from app.models.schemas import UserSettingsCreate, UserSettingsUpdate, UserSettingsSyncPayload
from app.utils.logger import debugLog, infoLog, errorLog

MODULE_NAME = "CRUDUserSettings"


def get_user_settings(db: Session, user_id: str) -> Optional[UserSettings]:
    """Lädt die Settings für einen Benutzer"""
    debugLog(MODULE_NAME, f"Lade Settings für User {user_id}")
    return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()


def create_user_settings(db: Session, *, settings_in: UserSettingsCreate) -> UserSettings:
    """Erstellt neue UserSettings"""
    debugLog(MODULE_NAME, f"Erstelle Settings für User {settings_in.user_id}")

    # Convert list to JSON string for database storage
    enabled_categories_json = json.dumps(settings_in.enabled_log_categories)

    db_settings = UserSettings(
        user_id=settings_in.user_id,
        log_level=settings_in.log_level,
        enabled_log_categories=enabled_categories_json,
        history_retention_days=settings_in.history_retention_days,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(db_settings)
    db.commit()
    db.refresh(db_settings)

    infoLog(MODULE_NAME, f"Settings für User {settings_in.user_id} erfolgreich erstellt")
    return db_settings


def update_user_settings(
    db: Session,
    *,
    db_obj: UserSettings,
    obj_in: UserSettingsUpdate
) -> UserSettings:
    """Aktualisiert bestehende UserSettings mit LWW-Konfliktlösung"""
    debugLog(MODULE_NAME, f"Aktualisiere Settings für User {db_obj.user_id}")

    # Last-Write-Wins Konfliktlösung
    if obj_in.updated_at and db_obj.updated_at:
        if obj_in.updated_at <= db_obj.updated_at:
            debugLog(
                MODULE_NAME,
                f"Settings-Update übersprungen - lokale Version ist neuer",
                details={
                    "incoming_timestamp": obj_in.updated_at.isoformat(),
                    "local_timestamp": db_obj.updated_at.isoformat()
                }
            )
            return db_obj

    # Convert list to JSON string for database storage
    enabled_categories_json = json.dumps(obj_in.enabled_log_categories)

    # Update fields
    db_obj.log_level = obj_in.log_level
    db_obj.enabled_log_categories = enabled_categories_json
    db_obj.history_retention_days = obj_in.history_retention_days
    db_obj.updated_at = obj_in.updated_at if obj_in.updated_at else datetime.utcnow()

    db.commit()
    db.refresh(db_obj)

    infoLog(MODULE_NAME, f"Settings für User {db_obj.user_id} erfolgreich aktualisiert")
    return db_obj


def sync_user_settings(
    db: Session,
    *,
    user_id: str,
    settings_payload: UserSettingsSyncPayload
) -> UserSettings:
    """Synchronisiert UserSettings (Create oder Update basierend auf Existenz)"""
    debugLog(MODULE_NAME, f"Synchronisiere Settings für User {user_id}")

    existing_settings = get_user_settings(db, user_id)

    if existing_settings:
        # Update existing settings
        update_data = UserSettingsUpdate(
            log_level=settings_payload.log_level,
            enabled_log_categories=settings_payload.enabled_log_categories,
            history_retention_days=settings_payload.history_retention_days,
            updated_at=settings_payload.updated_at
        )
        return update_user_settings(db, db_obj=existing_settings, obj_in=update_data)
    else:
        # Create new settings
        create_data = UserSettingsCreate(
            user_id=user_id,
            log_level=settings_payload.log_level,
            enabled_log_categories=settings_payload.enabled_log_categories,
            history_retention_days=settings_payload.history_retention_days
        )
        return create_user_settings(db, settings_in=create_data)


def get_user_settings_as_dict(db: Session, user_id: str) -> Optional[dict]:
    """Lädt UserSettings und konvertiert sie in ein Frontend-kompatibles Dict"""
    settings = get_user_settings(db, user_id)
    if not settings:
        return None

    try:
        # Parse JSON string back to list
        enabled_categories = json.loads(settings.enabled_log_categories)
    except (json.JSONDecodeError, TypeError):
        # Fallback to default if JSON parsing fails
        enabled_categories = ["store", "ui", "service"]
        errorLog(
            MODULE_NAME,
            f"Fehler beim Parsen der enabled_log_categories für User {user_id}",
            details={"raw_value": settings.enabled_log_categories}
        )

    return {
        "id": settings.id,
        "user_id": settings.user_id,
        "log_level": settings.log_level,
        "enabled_log_categories": enabled_categories,
        "history_retention_days": settings.history_retention_days,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at
    }


def create_default_user_settings(db: Session, user_id: str) -> UserSettings:
    """Erstellt Default-Settings für einen neuen Benutzer"""
    debugLog(MODULE_NAME, f"Erstelle Default-Settings für neuen User {user_id}")

    default_settings = UserSettingsCreate(
        user_id=user_id,
        log_level="INFO",
        enabled_log_categories=["store", "ui", "service"],
        history_retention_days=60
    )

    return create_user_settings(db, settings_in=default_settings)
