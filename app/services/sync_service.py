from sqlalchemy.orm import Session
from typing import Optional # Added for Optional WebSocket
from fastapi import WebSocket # Added for WebSocket type hint
from app.websocket.schemas import SyncQueueEntry, EntityType, SyncOperationType, AccountPayload, AccountGroupPayload, DeletePayload, DataUpdateNotificationMessage, ServerEventType
from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal
from app.models.financial_models import TenantBase, Account, AccountGroup # Import Account and AccountGroup models
from app.crud import crud_account, crud_account_group
from app.utils.logger import infoLog, errorLog, debugLog
from app.websocket.connection_manager import manager as websocket_manager_instance # Import the global manager
from datetime import datetime # Import datetime for comparison
import sqlite3 # Import sqlite3 to catch specific operational errors

MODULE_NAME = "SyncService"

def get_tenant_db_session(tenant_id: str) -> Session:
    """
    Initializes the tenant database if it doesn't exist and returns a new session.
    Ensures all tables defined in TenantBase (from financial_models) are created.
    """
    engine = create_tenant_db_engine(tenant_id)
    # Ensure all tables from financial_models.TenantBase are created
    TenantBase.metadata.create_all(bind=engine)

    # Configure the sessionmaker with the specific engine for this tenant
    TenantSessionLocal.configure(bind=engine)

    db = TenantSessionLocal()
    return db

async def process_sync_entry(entry: SyncQueueEntry, source_websocket: Optional[WebSocket] = None) -> tuple[bool, Optional[str]]:
    """
    Processes a single SyncQueueEntry, applies LWW, performs CRUD, and notifies clients.
    Returns a tuple: (success: bool, reason: Optional[str])
    'reason' is provided if success is False.
    """
    debugLog(MODULE_NAME, f"Processing sync entry: {entry.id} for tenant {entry.tenantId}", details={**entry.model_dump(), "has_source_websocket": bool(source_websocket)})

    db: Optional[Session] = None
    try:
        db = get_tenant_db_session(entry.tenantId)
        if db is None: # Should not happen if get_tenant_db_session raises an error on failure
            error_msg = f"Could not get DB session for tenant {entry.tenantId}"
            errorLog(MODULE_NAME, error_msg, details={"entry_id": entry.id})
            return False, error_msg

        entity_type = entry.entityType
        operation_type = entry.operationType
        payload = entry.payload # This is AccountPayload or AccountGroupPayload or DeletePayload
        entity_id = entry.entityId
        incoming_updated_at: Optional[datetime] = getattr(payload, 'updated_at', None) if payload else None

        notification_data: Optional[AccountPayload | AccountGroupPayload | DeletePayload] = None
        authoritative_data_used = False # Flag to indicate if DB data was sent because incoming was old

        if entity_type == EntityType.ACCOUNT:
            if not isinstance(payload, (AccountPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Account operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_account = crud_account.get_account(db=db, account_id=entity_id)
                if existing_account: # Treat as update if ID already exists (rare case, but LWW applies)
                    if incoming_updated_at and existing_account.updatedAt and incoming_updated_at > existing_account.updatedAt:
                        updated_account = crud_account.update_account(db=db, db_account=existing_account, account_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(updated_account)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(existing_account) # Send existing
                        authoritative_data_used = True
                else:
                    if isinstance(payload, AccountPayload):
                        new_account = crud_account.create_account(db=db, account_in=payload)
                        infoLog(MODULE_NAME, f"Created Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(new_account)
                    else: # Should not happen if previous check is fine
                        error_msg = "Payload mismatch for Account CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                if not isinstance(payload, AccountPayload):
                     error_msg = "Invalid payload type for Account UPDATE"
                     errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                     return False, error_msg
                db_account = crud_account.get_account(db=db, account_id=entity_id)
                if db_account:
                    if incoming_updated_at and db_account.updatedAt and incoming_updated_at > db_account.updatedAt:
                        updated_account = crud_account.update_account(db=db, db_account=db_account, account_in=payload)
                        infoLog(MODULE_NAME, f"Updated Account {entity_id} (LWW win)", details=payload)
                        notification_data = AccountPayload.model_validate(updated_account)
                    else:
                        infoLog(MODULE_NAME, f"Skipped Account UPDATE {entity_id} (LWW loss/equal or no timestamp)", details=payload)
                        notification_data = AccountPayload.model_validate(db_account) # Send existing authoritative data
                        authoritative_data_used = True
                else:
                    # If not found, create it (upsert behavior for updates from sync queue)
                    # This handles cases where a create might have been missed by the server but client has it
                    new_account = crud_account.create_account(db=db, account_in=payload)
                    infoLog(MODULE_NAME, f"Created Account {entity_id} during UPDATE (upsert)", details=payload)
                    notification_data = AccountPayload.model_validate(new_account)

            elif operation_type == SyncOperationType.DELETE:
                deleted_account = crud_account.delete_account(db=db, account_id=entity_id)
                if deleted_account:
                    infoLog(MODULE_NAME, f"Deleted Account {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"Account {entity_id} not found for DELETE (already deleted or never existed)")
                    # Send delete notification anyway to ensure client consistency
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True # Technically, non-existence is authoritative

        elif entity_type == EntityType.ACCOUNT_GROUP:
            if not isinstance(payload, (AccountGroupPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for AccountGroup operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_group = crud_account_group.get_account_group(db=db, account_group_id=entity_id)
                if existing_group: # Treat as update
                    if incoming_updated_at and existing_group.updatedAt and incoming_updated_at > existing_group.updatedAt:
                        updated_group = crud_account_group.update_account_group(db=db, db_account_group=existing_group, account_group_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for AccountGroup {entity_id}", details=payload)
                        notification_data = AccountGroupPayload.model_validate(updated_group)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for AccountGroup {entity_id}", details=payload)
                        notification_data = AccountGroupPayload.model_validate(existing_group)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, AccountGroupPayload):
                        new_group = crud_account_group.create_account_group(db=db, account_group_in=payload)
                        infoLog(MODULE_NAME, f"Created AccountGroup {entity_id}", details=payload)
                        notification_data = AccountGroupPayload.model_validate(new_group)
                    else:
                        error_msg = "Payload mismatch for AccountGroup CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                if not isinstance(payload, AccountGroupPayload):
                     error_msg = "Invalid payload type for AccountGroup UPDATE"
                     errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                     return False, error_msg
                db_account_group = crud_account_group.get_account_group(db=db, account_group_id=entity_id)
                if db_account_group:
                    if incoming_updated_at and db_account_group.updatedAt and incoming_updated_at > db_account_group.updatedAt:
                        updated_group = crud_account_group.update_account_group(db=db, db_account_group=db_account_group, account_group_in=payload)
                        infoLog(MODULE_NAME, f"Updated AccountGroup {entity_id} (LWW win)", details=payload)
                        notification_data = AccountGroupPayload.model_validate(updated_group)
                    else:
                        infoLog(MODULE_NAME, f"Skipped AccountGroup UPDATE {entity_id} (LWW loss/equal or no timestamp)", details=payload)
                        notification_data = AccountGroupPayload.model_validate(db_account_group)
                        authoritative_data_used = True
                else:
                    new_group = crud_account_group.create_account_group(db=db, account_group_in=payload)
                    infoLog(MODULE_NAME, f"Created AccountGroup {entity_id} during UPDATE (upsert)", details=payload)
                    notification_data = AccountGroupPayload.model_validate(new_group)

            elif operation_type == SyncOperationType.DELETE:
                deleted_group = crud_account_group.delete_account_group(db=db, account_group_id=entity_id)
                if deleted_group:
                    infoLog(MODULE_NAME, f"Deleted AccountGroup {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"AccountGroup {entity_id} not found for DELETE")
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True
        else:
            error_msg = f"Unknown entity type: {entity_type}"
            errorLog(MODULE_NAME, error_msg, details={"entry_id": entry.id})
            return False, error_msg

        # Send notification if data was processed or authoritative data needs to be sent
        if notification_data:
            # Determine the operation type for the notification.
            # If an incoming create/update was discarded due to LWW, the operation effectively becomes an "update"
            # with the authoritative data from the DB. For deletes, it's always delete.
            effective_operation_type = operation_type
            if authoritative_data_used and operation_type != SyncOperationType.DELETE:
                 # If we sent back the DB's version because incoming was old,
                 # it's like an update to the client with the current truth.
                 # If the item didn't exist and we tried to update (upsert failed due to LWW),
                 # then it's more complex. For now, treat as update with current state.
                 # If it was a create that lost LWW, we send the existing record (like an update).
                 effective_operation_type = SyncOperationType.UPDATE


            message = DataUpdateNotificationMessage(
                event_type=ServerEventType.DATA_UPDATE, # Ensure this matches schema
                tenant_id=entry.tenantId,
                entity_type=entity_type,
                operation_type=effective_operation_type, # Use effective operation type
                data=notification_data
            )
            await websocket_manager_instance.broadcast_json_to_tenant(
                message.model_dump(),
                entry.tenantId,
                exclude_websocket=source_websocket
            )
            debugLog(MODULE_NAME, f"Sent notification for {str(entity_type)} {entity_id}", details=message.model_dump())

        return True, None

    except sqlite3.OperationalError as oe:
        # Spezifische Behandlung für Datenbank-Operationen-Fehler (z.B. "no such table")
        error_msg = f"Database operational error processing sync entry {entry.id} for tenant {entry.tenantId}: {str(oe)}"
        error_reason = "database_operational_error"
        if "no such table" in str(oe).lower():
            error_reason = "table_not_found"
        errorLog(MODULE_NAME, error_msg, details={"entry": entry.model_dump(), "error": str(oe), "reason": error_reason})
        return False, error_reason
    except Exception as e:
        # Allgemeine Fehlerbehandlung
        error_msg = f"Generic error processing sync entry {entry.id} for tenant {entry.tenantId}: {str(e)}"
        errorLog(MODULE_NAME, error_msg, details={"entry": entry.model_dump(), "error": str(e)})
        return False, "generic_processing_error"
    finally:
        if db:
            db.close()
