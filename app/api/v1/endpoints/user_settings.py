from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.db.database import get_db
from app.models.schemas import UserSettings, UserSettingsSyncPayload, UserSettingsUpdate
from app.crud import crud_user_settings
from app.utils.logger import debugLog, infoLog, errorLog

MODULE_NAME = "UserSettingsAPI"

router = APIRouter()


@router.get("/settings/{user_id}", response_model=Dict[str, Any])
def get_user_settings(
    user_id: str,
    db: Session = Depends(get_db)
):
    """Lädt die Settings für einen Benutzer"""
    debugLog(MODULE_NAME, f"API-Request: Lade Settings für User {user_id}")

    try:
        settings_dict = crud_user_settings.get_user_settings_as_dict(db, user_id)

        if not settings_dict:
            # Erstelle Default-Settings wenn keine vorhanden
            debugLog(MODULE_NAME, f"Keine Settings gefunden für User {user_id}, erstelle Defaults")
            default_settings = crud_user_settings.create_default_user_settings(db, user_id)
            settings_dict = crud_user_settings.get_user_settings_as_dict(db, user_id)

        infoLog(MODULE_NAME, f"Settings erfolgreich geladen für User {user_id}")
        return settings_dict

    except Exception as e:
        errorLog(
            MODULE_NAME,
            f"Fehler beim Laden der Settings für User {user_id}",
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Laden der Settings: {str(e)}"
        )


@router.post("/settings/{user_id}/sync", response_model=Dict[str, Any])
def sync_user_settings(
    user_id: str,
    settings_payload: UserSettingsSyncPayload,
    db: Session = Depends(get_db)
):
    """Synchronisiert UserSettings (Create oder Update)"""
    debugLog(
        MODULE_NAME,
        f"API-Request: Synchronisiere Settings für User {user_id}",
        details={
            "log_level": settings_payload.log_level.value,
            "categories_count": len(settings_payload.log_categories),
            "retention_days": settings_payload.history_retention_days,
            "updated_at": settings_payload.updated_at.isoformat() if settings_payload.updated_at else None
        }
    )

    try:
        updated_settings = crud_user_settings.sync_user_settings(
            db,
            user_id=user_id,
            settings_payload=settings_payload
        )

        # Convert to dict for response
        settings_dict = crud_user_settings.get_user_settings_as_dict(db, user_id)

        infoLog(MODULE_NAME, f"Settings erfolgreich synchronisiert für User {user_id}")
        return settings_dict

    except Exception as e:
        errorLog(
            MODULE_NAME,
            f"Fehler beim Synchronisieren der Settings für User {user_id}",
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Synchronisieren der Settings: {str(e)}"
        )


@router.put("/settings/{user_id}", response_model=Dict[str, Any])
def update_user_settings(
    user_id: str,
    settings_update: UserSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Aktualisiert UserSettings"""
    debugLog(MODULE_NAME, f"API-Request: Aktualisiere Settings für User {user_id}")

    try:
        existing_settings = crud_user_settings.get_user_settings(db, user_id)

        if not existing_settings:
            # Erstelle Settings wenn keine vorhanden
            debugLog(MODULE_NAME, f"Keine Settings gefunden für User {user_id}, erstelle neue")
            crud_user_settings.create_default_user_settings(db, user_id)
            existing_settings = crud_user_settings.get_user_settings(db, user_id)

        updated_settings = crud_user_settings.update_user_settings(
            db,
            db_obj=existing_settings,
            obj_in=settings_update
        )

        # Convert to dict for response
        settings_dict = crud_user_settings.get_user_settings_as_dict(db, user_id)

        infoLog(MODULE_NAME, f"Settings erfolgreich aktualisiert für User {user_id}")
        return settings_dict

    except Exception as e:
        errorLog(
            MODULE_NAME,
            f"Fehler beim Aktualisieren der Settings für User {user_id}",
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Aktualisieren der Settings: {str(e)}"
        )


@router.post("/settings/{user_id}/reset", response_model=Dict[str, Any])
def reset_user_settings_to_defaults(
    user_id: str,
    db: Session = Depends(get_db)
):
    """Setzt UserSettings auf Standardwerte zurück"""
    debugLog(MODULE_NAME, f"API-Request: Setze Settings zurück für User {user_id}")

    try:
        # Lösche bestehende Settings
        existing_settings = crud_user_settings.get_user_settings(db, user_id)
        if existing_settings:
            db.delete(existing_settings)
            db.commit()

        # Erstelle neue Default-Settings
        default_settings = crud_user_settings.create_default_user_settings(db, user_id)
        settings_dict = crud_user_settings.get_user_settings_as_dict(db, user_id)

        infoLog(MODULE_NAME, f"Settings erfolgreich zurückgesetzt für User {user_id}")
        return settings_dict

    except Exception as e:
        errorLog(
            MODULE_NAME,
            f"Fehler beim Zurücksetzen der Settings für User {user_id}",
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Zurücksetzen der Settings: {str(e)}"
        )
