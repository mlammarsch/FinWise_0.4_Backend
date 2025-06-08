from sqlalchemy.orm import Session
from typing import Optional  # Added for Optional WebSocket
from fastapi import WebSocket  # Added for WebSocket type hint
from app.websocket.schemas import (
    SyncQueueEntry, EntityType, SyncOperationType,
    AccountPayload, AccountGroupPayload, DeletePayload,
    DataUpdateNotificationMessage, ServerEventType, InitialDataPayload
)
from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal
from app.models.financial_models import TenantBase, Account, AccountGroup  # Import Account and AccountGroup models
from app.crud import crud_account, crud_account_group
from app.utils.logger import infoLog, errorLog, debugLog
from app.websocket.connection_manager import manager as websocket_manager_instance  # Import the global manager
from datetime import datetime  # Import datetime for comparison
import sqlite3  # Import sqlite3 to catch specific operational errors

MODULE_NAME = "SyncService"


def get_tenant_db_session(tenant_id: str) -> Session:
    engine = create_tenant_db_engine(tenant_id)
    TenantBase.metadata.create_all(bind=engine)
    TenantSessionLocal.configure(bind=engine)

    db = TenantSessionLocal()
    return db


async def process_sync_entry(entry: SyncQueueEntry, source_websocket: Optional[WebSocket] = None) -> tuple[bool, Optional[str]]:
    """Processes a sync entry, handling LWW, CRUD operations, and client notifications."""
    debugLog(MODULE_NAME, f"Processing sync entry: {entry.id} for tenant {entry.tenantId}", details={**entry.model_dump(), "has_source_websocket": bool(source_websocket)})

    db: Optional[Session] = None
    try:
        db = get_tenant_db_session(entry.tenantId)
        if db is None:
            error_msg = f"Could not get DB session for tenant {entry.tenantId}"
            errorLog(MODULE_NAME, error_msg, details={"entry_id": entry.id})
            return False, error_msg

        entity_type = entry.entityType
        operation_type = entry.operationType
        payload = entry.payload  # This is AccountPayload or AccountGroupPayload or DeletePayload
        entity_id = entry.entityId
        incoming_updated_at: Optional[datetime] = getattr(payload, 'updated_at', None) if payload else None

        notification_data: Optional[AccountPayload | AccountGroupPayload | DeletePayload] = None
        authoritative_data_used = False  # Flag to indicate if DB data was sent because incoming was old

        if entity_type == EntityType.ACCOUNT:
            if not isinstance(payload, (AccountPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Account operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_account = crud_account.get_account(db=db, account_id=entity_id)
                if existing_account:  # Treat as update if ID already exists (rare case, but LWW applies)
                    if incoming_updated_at and existing_account.updatedAt and incoming_updated_at > existing_account.updatedAt:
                        updated_account = crud_account.update_account(db=db, db_account=existing_account, account_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(updated_account)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(existing_account)  # Send existing
                        authoritative_data_used = True
                else:
                    if isinstance(payload, AccountPayload):
                        new_account = crud_account.create_account(db=db, account_in=payload)
                        infoLog(MODULE_NAME, f"Created Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(new_account)
                    else:  # Should not happen if previous check is fine
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
                        notification_data = AccountPayload.model_validate(db_account)  # Send existing authoritative data
                        authoritative_data_used = True
                else:
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
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True  # Technically, non-existence is authoritative

        elif entity_type == EntityType.ACCOUNT_GROUP:
            if not isinstance(payload, (AccountGroupPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for AccountGroup operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_group = crud_account_group.get_account_group(db=db, account_group_id=entity_id)
                if existing_group:  # Treat as update
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

        if notification_data:
            effective_operation_type = operation_type
            if authoritative_data_used and operation_type != SyncOperationType.DELETE:
                effective_operation_type = SyncOperationType.UPDATE

            message = DataUpdateNotificationMessage(
                event_type=ServerEventType.DATA_UPDATE,  # Ensure this matches schema
                tenant_id=entry.tenantId,
                entity_type=entity_type,
                operation_type=effective_operation_type,  # Use effective operation type
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
        error_msg = f"Database operational error processing sync entry {entry.id} for tenant {entry.tenantId}: {str(oe)}"
        error_reason = "database_operational_error"
        if "no such table" in str(oe).lower():
            error_reason = "table_not_found"
        errorLog(MODULE_NAME, error_msg, details={"entry": entry.model_dump(), "error": str(oe), "reason": error_reason})
        return False, error_reason
    except Exception as e:
        error_msg = f"Generic error processing sync entry {entry.id} for tenant {entry.tenantId}: {str(e)}"
        errorLog(MODULE_NAME, error_msg, details={"entry": entry.model_dump(), "error": str(e)})
        return False, "generic_processing_error"
    finally:
        if db:
            db.close()


async def get_initial_data_for_tenant(tenant_id: str) -> tuple[Optional[InitialDataPayload], Optional[str]]:
    """Fetches initial data (accounts, groups) for a tenant on connection."""
    debugLog(MODULE_NAME, f"Attempting to get initial data for tenant {tenant_id}")
    db: Optional[Session] = None
    try:
        db = get_tenant_db_session(tenant_id)
        if db is None:
            error_msg = f"Could not get DB session for tenant {tenant_id} during initial data fetch."
            errorLog(MODULE_NAME, error_msg)
            return None, error_msg

        accounts_db = crud_account.get_accounts(db=db)
        account_groups_db = crud_account_group.get_account_groups(db=db)

        accounts_payload = [AccountPayload.model_validate(acc) for acc in accounts_db]
        account_groups_payload = [AccountGroupPayload.model_validate(ag) for ag in account_groups_db]

        initial_data = InitialDataPayload(
            accounts=accounts_payload,
            account_groups=account_groups_payload
        )
        infoLog(MODULE_NAME, f"Successfully retrieved initial data for tenant {tenant_id}. Accounts: {len(accounts_payload)}, AccountGroups: {len(account_groups_payload)}")
        return initial_data, None

    except sqlite3.OperationalError as oe:
        error_msg = f"Database operational error fetching initial data for tenant {tenant_id}: {str(oe)}"
        error_reason = "database_operational_error"
        if "no such table" in str(oe).lower():
            error_reason = "table_not_found"
        errorLog(MODULE_NAME, error_msg, details={"tenant_id": tenant_id, "error": str(oe), "reason": error_reason})
        return None, error_reason
    except Exception as e:
        error_msg = f"Generic error fetching initial data for tenant {tenant_id}: {str(e)}"
        errorLog(MODULE_NAME, error_msg, details={"tenant_id": tenant_id, "error": str(e)})
        return None, "generic_initial_data_error"
    finally:
        if db:
            db.close()
