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

        # 2. Zuerst alle WebSocket-Verbindungen für diesen Mandanten schließen
        debugLog(MODULE_NAME, f"Attempting to close WebSocket connections for tenant {tenant_id} before file deletion.",
                {"tenant_id": tenant_id})
        await manager.close_connections_for_tenant(tenant_id, reason="Tenant deletion process initiated")
        infoLog(MODULE_NAME, f"WebSocket connections for tenant {tenant_id} requested to close.",
                {"tenant_id": tenant_id})

        # Kurze Pause, um den Verbindungen Zeit zum Schließen zu geben, bevor die Datei gelöscht wird.
        # Dies ist ein Workaround und sollte idealerweise durch einen robusteren Mechanismus ersetzt werden,
        # der sicherstellt, dass alle Ressourcen freigegeben sind.
        import asyncio
        await asyncio.sleep(0.5) # 500ms Pause

        # 3. Mandanten-DB-Datei löschen (vor DB-Löschung für bessere Fehlerbehandlung)
        debugLog(MODULE_NAME, f"Proceeding to delete database file for tenant {tenant_id}.",
                {"tenant_id": tenant_id})
        tenant_db_deleted = await TenantService._delete_tenant_database_file(tenant_id)
        if not tenant_db_deleted:
            warnLog(MODULE_NAME, f"Could not delete tenant database file for {tenant_id}, continuing with DB deletion",
                   {"tenant_id": tenant_id})

        # 4. Mandant aus Haupt-DB löschen
        try:
            deleted_tenant = crud.delete_tenant(db, tenant_id=tenant_id)
            if not deleted_tenant:
                errorLog(MODULE_NAME, f"Failed to delete tenant {tenant_id} from main database",
                        {"tenant_id": tenant_id})
                return None

            infoLog(MODULE_NAME, f"Tenant {tenant_id} successfully deleted completely",
                   {"tenant_id": tenant_id, "tenant_name": deleted_tenant.name, "db_file_deleted": tenant_db_deleted})

            # 5. WebSocket-Benachrichtigung an andere Clients senden (obwohl keine mehr verbunden sein sollten für diesen Tenant)
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
            # 2. WebSocket-Verbindungen schließen
            debugLog(MODULE_NAME, f"Attempting to close WebSocket connections for tenant {tenant_id} before database reset.",
                    {"tenant_id": tenant_id})
            await manager.close_connections_for_tenant(tenant_id, reason="Tenant database reset process initiated")
            infoLog(MODULE_NAME, f"WebSocket connections for tenant {tenant_id} requested to close for reset.",
                    {"tenant_id": tenant_id})

            import asyncio # Sicherstellen, dass asyncio importiert ist
            await asyncio.sleep(0.5) # Kurze Pause

            # 3. Mandanten-DB-Datei löschen und neu erstellen
            tenant_db_deleted = await TenantService._delete_tenant_database_file(tenant_id)
            if not tenant_db_deleted:
                warnLog(MODULE_NAME, f"Could not delete existing tenant database file for {tenant_id}",
                       {"tenant_id": tenant_id})

            # 4. Neue Mandanten-DB mit Tabellen erstellen
            create_tenant_specific_tables(tenant_id)

            infoLog(MODULE_NAME, f"Tenant database successfully reset for {tenant_id}",
                   {"tenant_id": tenant_id, "tenant_name": db_tenant.name})

            # 5. WebSocket-Benachrichtigung an Clients senden
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
        """Löscht die physische SQLite-Datei für einen Mandanten mit mehreren Versuchen."""
        # Importiere die benötigten Funktionen
        from ..db.database import dispose_tenant_engine
        from ..api.deps import close_tenant_db_connection

        if not TENANT_DATABASE_DIR:
            errorLog(MODULE_NAME, "TENANT_DATABASE_DIR not configured", {"tenant_id": tenant_id})
            return False

        db_filename = f"finwiseTenantDB_{tenant_id}.db"
        db_path = os.path.join(TENANT_DATABASE_DIR, db_filename)

        if not os.path.exists(db_path):
            debugLog(MODULE_NAME, f"Tenant database file does not exist (already deleted?): {db_path}",
                    {"tenant_id": tenant_id, "file_path": db_path})
            return True # Ziel erreicht, wenn Datei nicht existiert

        # 1. Zuerst alle aktiven Verbindungen aus dem deps-Modul schließen
        debugLog(MODULE_NAME, f"Attempting to close active tenant connections for {tenant_id} before file deletion.",
                {"tenant_id": tenant_id})
        close_tenant_db_connection(tenant_id)

        # 2. Dann die Engine disposen, um alle Verbindungen im Pool zu schließen
        debugLog(MODULE_NAME, f"Attempting to dispose engine for tenant {tenant_id} before file deletion.",
                {"tenant_id": tenant_id})
        dispose_tenant_engine(tenant_id)
        infoLog(MODULE_NAME, f"Engine for tenant {tenant_id} requested to dispose.",
                {"tenant_id": tenant_id})

        # 3. SQLite-spezifische Verbindungen schließen
        try:
            import sqlite3
            # Versuche alle SQLite-Verbindungen zu dieser Datei zu schließen
            debugLog(MODULE_NAME, f"Attempting to close SQLite connections for {db_path}",
                    {"tenant_id": tenant_id, "db_path": db_path})
        except Exception as e:
            debugLog(MODULE_NAME, f"Error during SQLite connection cleanup: {str(e)}",
                    {"tenant_id": tenant_id, "error": str(e)})

        # 4. Längere Pause nach dem dispose, um sicherzustellen, dass alle Operationen abgeschlossen sind
        import asyncio
        await asyncio.sleep(1.0) # 1000ms Pause für vollständige Freigabe

        # Mehrere Löschversuche mit längeren Wartezeiten
        max_attempts = 5
        wait_times = [0.5, 1.0, 2.0, 3.0, 5.0] # Wartezeiten in Sekunden für jeden Versuch

        for attempt in range(max_attempts):
            try:
                debugLog(MODULE_NAME, f"Attempt {attempt + 1} to delete tenant database file: {db_path}",
                        {"tenant_id": tenant_id, "attempt": attempt + 1, "max_attempts": max_attempts})
                os.remove(db_path)
                infoLog(MODULE_NAME, f"Successfully deleted tenant database file on attempt {attempt + 1}: {db_path}",
                       {"tenant_id": tenant_id, "file_path": db_path, "attempt": attempt + 1})
                return True
            except OSError as e:
                errorLog(MODULE_NAME, f"OS error on attempt {attempt + 1} deleting tenant database file for {tenant_id}. Path: {db_path}",
                        {"tenant_id": tenant_id, "file_path": db_path, "attempt": attempt + 1, "error_type": type(e).__name__, "error": str(e)})
                if attempt < max_attempts - 1:
                    wait_duration = wait_times[attempt]
                    warnLog(MODULE_NAME, f"Waiting {wait_duration}s before next delete attempt for {tenant_id}.",
                            {"tenant_id": tenant_id, "wait_duration": wait_duration})
                    import asyncio # Import hier, da es nur in diesem Block benötigt wird
                    await asyncio.sleep(wait_duration)
                else:
                    errorLog(MODULE_NAME, f"Failed to delete tenant database file for {tenant_id} after {max_attempts} attempts. Path: {db_path}",
                            {"tenant_id": tenant_id, "file_path": db_path, "max_attempts": max_attempts})
                    return False # Alle Versuche fehlgeschlagen
            except Exception as e: # Andere unerwartete Fehler
                errorLog(MODULE_NAME, f"Unexpected error on attempt {attempt + 1} deleting tenant database file for {tenant_id}. Path: {db_path}",
                        {"tenant_id": tenant_id, "file_path": db_path, "attempt": attempt + 1, "error_type": type(e).__name__, "error": str(e)})
                return False # Bei unerwarteten Fehlern sofort abbrechen

        return False # Sollte nicht erreicht werden, wenn die Logik korrekt ist

    @staticmethod
    async def _notify_tenant_deletion(tenant_id: str, tenant_name: str):
        """Sendet WebSocket-Benachrichtigung über Mandanten-Löschung"""
        try:
            # Benachrichtigung an alle Clients des Mandanten senden
            delete_message = DataUpdateNotificationMessage(
                tenant_id=tenant_id,
                entity_type="Tenant", # Wird automatisch zu EntityType.TENANT durch Pydantic Validierung
                operation_type="delete", # Wird automatisch zu SyncOperationType.DELETE
                data={"id": tenant_id, "name": tenant_name} # Wird zu DeletePayload
            )

            dumped_message = delete_message.model_dump()
            debugLog(
                MODULE_NAME,
                f"Dumped tenant deletion notification for {tenant_id}",
                details={
                    "tenant_id": tenant_id,
                    "dumped_message_type": type(dumped_message),
                    "dumped_message_content": str(dumped_message),
                    "original_event_type_in_model": type(delete_message.event_type),
                    "original_entity_type_in_model": type(delete_message.entity_type),
                    "original_operation_type_in_model": type(delete_message.operation_type)
                }
            )

            await manager.broadcast_json_to_tenant(
                dumped_message, # Sicherstellen, dass das gedumpte Objekt verwendet wird
                tenant_id
            )

            debugLog(MODULE_NAME, f"Sent tenant deletion notification for {tenant_id}",
                    {"tenant_id": tenant_id, "tenant_name": tenant_name})

        except Exception as e:
            errorLog(MODULE_NAME, f"Error sending tenant deletion notification for {tenant_id}",
                    {"tenant_id": tenant_id, "error_type": type(e).__name__, "error": str(e)})

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
