import os
import sqlite3
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from typing import Optional, Dict, Any
from ..db import crud
from ..models import user_tenant_models as models
from ..config import TENANT_DATABASE_DIR
from ..db.database import get_tenant_db_url, create_tenant_specific_tables
from ..utils.logger import infoLog, errorLog, debugLog, warnLog
from ..websocket.connection_manager import manager
from ..websocket.schemas import DataUpdateNotificationMessage

MODULE_NAME = "services.tenant_service"

class TenantService:
    """Service für erweiterte Mandanten-Verwaltung"""

    @staticmethod
    async def delete_tenant_completely(db: Session, tenant_id: str, user_id: str) -> Optional[models.Tenant]:
        """
        Löscht einen Mandanten vollständig:
        1. Validiert Berechtigung (nur Owner kann löschen)
        2. Löscht Mandanten-Eintrag aus Haupt-DB
        3. Löscht entsprechende SQLite-Datei
        4. Benachrichtigt andere Clients via WebSocket
        """
        debugLog(MODULE_NAME, f"Attempting complete tenant deletion for ID: {tenant_id}",
                {"tenant_id": tenant_id, "user_id": user_id})

        # 1. Mandant aus DB abrufen und Berechtigung prüfen
        db_tenant = crud.get_tenant(db, tenant_id=tenant_id)
        if not db_tenant:
            warnLog(MODULE_NAME, f"Tenant with ID {tenant_id} not found for deletion",
                   {"tenant_id": tenant_id, "user_id": user_id})
            return None

        # Berechtigung prüfen: Nur der Owner (user_id) kann den Mandanten löschen
        if db_tenant.user_id != user_id:
            errorLog(MODULE_NAME, f"User {user_id} not authorized to delete tenant {tenant_id}",
                    {"tenant_id": tenant_id, "user_id": user_id, "owner_id": db_tenant.user_id})
            raise PermissionError(f"User {user_id} is not authorized to delete tenant {tenant_id}")

        # 2. Mandanten-DB-Datei löschen (vor DB-Löschung für bessere Fehlerbehandlung)
        tenant_db_deleted = await TenantService._delete_tenant_database_file(tenant_id)
        if not tenant_db_deleted:
            warnLog(MODULE_NAME, f"Could not delete tenant database file for {tenant_id}, continuing with DB deletion",
                   {"tenant_id": tenant_id})

        # 3. Mandant aus Haupt-DB löschen
        try:
            deleted_tenant = crud.delete_tenant(db, tenant_id=tenant_id)
            if not deleted_tenant:
                errorLog(MODULE_NAME, f"Failed to delete tenant {tenant_id} from main database",
                        {"tenant_id": tenant_id})
                return None

            infoLog(MODULE_NAME, f"Tenant {tenant_id} successfully deleted completely",
                   {"tenant_id": tenant_id, "tenant_name": deleted_tenant.name, "db_file_deleted": tenant_db_deleted})

            # 4. WebSocket-Benachrichtigung an andere Clients senden
            await TenantService._notify_tenant_deletion(tenant_id, deleted_tenant.name)

            return deleted_tenant

        except Exception as e:
            errorLog(MODULE_NAME, f"Error during complete tenant deletion for {tenant_id}",
                    {"tenant_id": tenant_id, "error": str(e)})
            raise

    @staticmethod
    async def reset_tenant_database(db: Session, tenant_id: str, user_id: str) -> bool:
        """
        Setzt die Mandanten-Datenbank zurück:
        1. Validiert Berechtigung
        2. Löscht alle Inhalte aller Tabellen
        3. Führt Initial-Setup durch
        4. Behält Mandanten-Eintrag in Haupt-DB bei
        """
        debugLog(MODULE_NAME, f"Attempting tenant database reset for ID: {tenant_id}",
                {"tenant_id": tenant_id, "user_id": user_id})

        # 1. Mandant abrufen und Berechtigung prüfen
        db_tenant = crud.get_tenant(db, tenant_id=tenant_id)
        if not db_tenant:
            warnLog(MODULE_NAME, f"Tenant with ID {tenant_id} not found for database reset",
                   {"tenant_id": tenant_id, "user_id": user_id})
            return False

        # Berechtigung prüfen
        if db_tenant.user_id != user_id:
            errorLog(MODULE_NAME, f"User {user_id} not authorized to reset database for tenant {tenant_id}",
                    {"tenant_id": tenant_id, "user_id": user_id, "owner_id": db_tenant.user_id})
            raise PermissionError(f"User {user_id} is not authorized to reset database for tenant {tenant_id}")

        try:
            # 2. Mandanten-DB-Datei löschen und neu erstellen
            tenant_db_deleted = await TenantService._delete_tenant_database_file(tenant_id)
            if not tenant_db_deleted:
                warnLog(MODULE_NAME, f"Could not delete existing tenant database file for {tenant_id}",
                       {"tenant_id": tenant_id})

            # 3. Neue Mandanten-DB mit Tabellen erstellen
            create_tenant_specific_tables(tenant_id)

            infoLog(MODULE_NAME, f"Tenant database successfully reset for {tenant_id}",
                   {"tenant_id": tenant_id, "tenant_name": db_tenant.name})

            # 4. WebSocket-Benachrichtigung an Clients senden
            await TenantService._notify_tenant_database_reset(tenant_id, db_tenant.name)

            return True

        except Exception as e:
            errorLog(MODULE_NAME, f"Error during tenant database reset for {tenant_id}",
                    {"tenant_id": tenant_id, "error": str(e)})
            raise

    @staticmethod
    async def clear_sync_queue(tenant_id: str, user_id: str) -> bool:
        """
        Löscht alle SyncQueue-Einträge für den Mandanten.
        Nur für Debugging/Wartung gedacht.
        """
        debugLog(MODULE_NAME, f"Attempting to clear sync queue for tenant: {tenant_id}",
                {"tenant_id": tenant_id, "user_id": user_id})

        try:
            # Mandanten-DB-Verbindung herstellen
            tenant_db_url = get_tenant_db_url(tenant_id)
            engine = create_engine(tenant_db_url, connect_args={"check_same_thread": False})

            # SyncQueue-Tabelle leeren (falls sie existiert)
            with engine.connect() as connection:
                # Prüfen ob sync_queue Tabelle existiert
                result = connection.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_queue'"
                ))
                table_exists = result.fetchone() is not None

                if table_exists:
                    # Anzahl Einträge vor Löschung ermitteln
                    count_result = connection.execute(text("SELECT COUNT(*) FROM sync_queue"))
                    entry_count = count_result.fetchone()[0]

                    # Alle Einträge löschen
                    connection.execute(text("DELETE FROM sync_queue"))
                    connection.commit()

                    infoLog(MODULE_NAME, f"Cleared {entry_count} sync queue entries for tenant {tenant_id}",
                           {"tenant_id": tenant_id, "entries_cleared": entry_count})
                else:
                    debugLog(MODULE_NAME, f"No sync_queue table found for tenant {tenant_id}",
                            {"tenant_id": tenant_id})

            return True

        except Exception as e:
            errorLog(MODULE_NAME, f"Error clearing sync queue for tenant {tenant_id}",
                    {"tenant_id": tenant_id, "error": str(e)})
            raise

    @staticmethod
    async def _delete_tenant_database_file(tenant_id: str) -> bool:
        """Löscht die physische SQLite-Datei für einen Mandanten"""
        try:
            if not TENANT_DATABASE_DIR:
                errorLog(MODULE_NAME, "TENANT_DATABASE_DIR not configured", {"tenant_id": tenant_id})
                return False

            db_filename = f"finwiseTenantDB_{tenant_id}.db"
            db_path = os.path.join(TENANT_DATABASE_DIR, db_filename)

            if os.path.exists(db_path):
                os.remove(db_path)
                infoLog(MODULE_NAME, f"Successfully deleted tenant database file: {db_path}",
                       {"tenant_id": tenant_id, "file_path": db_path})
                return True
            else:
                debugLog(MODULE_NAME, f"Tenant database file does not exist: {db_path}",
                        {"tenant_id": tenant_id, "file_path": db_path})
                return True  # Datei existiert nicht = Ziel erreicht

        except OSError as e:
            errorLog(MODULE_NAME, f"OS error deleting tenant database file for {tenant_id}",
                    {"tenant_id": tenant_id, "error": str(e)})
            return False
        except Exception as e:
            errorLog(MODULE_NAME, f"Unexpected error deleting tenant database file for {tenant_id}",
                    {"tenant_id": tenant_id, "error": str(e)})
            return False

    @staticmethod
    async def _notify_tenant_deletion(tenant_id: str, tenant_name: str):
        """Sendet WebSocket-Benachrichtigung über Mandanten-Löschung"""
        try:
            # Benachrichtigung an alle Clients des Mandanten senden
            delete_message = DataUpdateNotificationMessage(
                tenant_id=tenant_id,
                entity_type="Tenant",
                operation_type="delete",
                data={"id": tenant_id, "name": tenant_name}
            )

            await manager.broadcast_json_to_tenant(
                delete_message.model_dump(),
                tenant_id
            )

            debugLog(MODULE_NAME, f"Sent tenant deletion notification for {tenant_id}",
                    {"tenant_id": tenant_id, "tenant_name": tenant_name})

        except Exception as e:
            errorLog(MODULE_NAME, f"Error sending tenant deletion notification for {tenant_id}",
                    {"tenant_id": tenant_id, "error": str(e)})

    @staticmethod
    async def _notify_tenant_database_reset(tenant_id: str, tenant_name: str):
        """Sendet WebSocket-Benachrichtigung über Mandanten-DB-Reset"""
        try:
            # Benachrichtigung an alle Clients des Mandanten senden
            reset_message = DataUpdateNotificationMessage(
                tenant_id=tenant_id,
                entity_type="TenantDatabase",
                operation_type="reset",
                data={"id": tenant_id, "name": tenant_name, "action": "database_reset"}
            )

            await manager.broadcast_json_to_tenant(
                reset_message.model_dump(),
                tenant_id
            )

            debugLog(MODULE_NAME, f"Sent tenant database reset notification for {tenant_id}",
                    {"tenant_id": tenant_id, "tenant_name": tenant_name})

        except Exception as e:
            errorLog(MODULE_NAME, f"Error sending tenant database reset notification for {tenant_id}",
                    {"tenant_id": tenant_id, "error": str(e)})
