from sqlalchemy.orm import Session
from typing import Optional, Dict, List, Tuple  # Added for Optional WebSocket and type hints
from fastapi import WebSocket  # Added for WebSocket type hint
from app.websocket.schemas import (
    SyncQueueEntry, EntityType, SyncOperationType,
    AccountPayload, AccountGroupPayload, CategoryPayload, CategoryGroupPayload, RecipientPayload, TagPayload, AutomationRulePayload, PlanningTransactionPayload, TransactionPayload, DeletePayload,
    DataUpdateNotificationMessage, ServerEventType, InitialDataPayload,
    DataStatusResponseMessage, EntityChecksum
)
from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal
from app.models.financial_models import TenantBase, Account, AccountGroup, Category, CategoryGroup, Recipient, Tag, AutomationRule, PlanningTransaction, Transaction  # Import all models
from app.crud import crud_account, crud_account_group, crud_category, crud_category_group, crud_recipient, crud_tag, crud_automation_rule, crud_planning_transaction, crud_transaction
from app.utils.logger import infoLog, errorLog, debugLog, warnLog
from app.websocket.connection_manager import manager as websocket_manager_instance  # Import the global manager
from datetime import datetime  # Import datetime for comparison
import sqlite3  # Import sqlite3 to catch specific operational errors
import hashlib  # Import hashlib for checksum calculation
import json  # Import json for serialization
import time  # Import time for timestamps
from datetime import timezone  # Import timezone for datetime normalization

MODULE_NAME = "SyncService"


def normalize_datetime_for_comparison(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalisiert Datetime-Objekte für LWW-Vergleiche durch Konvertierung zu UTC."""
    if dt is None:
        return None

    # Wenn bereits timezone-aware, zu UTC konvertieren
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)

    # Wenn naive datetime, als UTC behandeln und timezone hinzufügen
    return dt.replace(tzinfo=timezone.utc)


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
        # Für Pydantic-Modelle mit Aliasen müssen wir die korrekten Attributnamen verwenden
        incoming_updated_at: Optional[datetime] = None
        if payload:
            if hasattr(payload, 'updated_at'):
                incoming_updated_at = payload.updated_at
            elif hasattr(payload, 'updatedAt'):
                incoming_updated_at = payload.updatedAt
        # Normalisiere incoming datetime für LWW-Vergleiche
        normalized_incoming_updated_at = normalize_datetime_for_comparison(incoming_updated_at)

        notification_data: Optional[AccountPayload | AccountGroupPayload | CategoryPayload | CategoryGroupPayload | RecipientPayload | TagPayload | AutomationRulePayload | PlanningTransactionPayload | DeletePayload] = None
        authoritative_data_used = False  # Flag to indicate if DB data was sent because incoming was old

        if entity_type == EntityType.ACCOUNT:
            if not isinstance(payload, (AccountPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Account operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_account = crud_account.get_account(db=db, account_id=entity_id)
                if existing_account:  # Treat as update if ID already exists (rare case, but LWW applies)
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_account.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_account = crud_account.update_account(db=db, db_account=existing_account, account_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(updated_account)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Account {entity_id}", details=payload)
                        notification_data = AccountPayload.model_validate(existing_account)  # Send existing
                        authoritative_data_used = True
                else:
                    if isinstance(payload, AccountPayload):
                        # Debug-Logging für accountType
                        debugLog(MODULE_NAME, f"Creating Account {entity_id} with accountType: {payload.accountType} (type: {type(payload.accountType)})")
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
                    normalized_db_updated_at = normalize_datetime_for_comparison(db_account.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
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
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_group.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
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
                    normalized_db_updated_at = normalize_datetime_for_comparison(db_account_group.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
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

        elif entity_type == EntityType.CATEGORY:
            if not isinstance(payload, (CategoryPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Category operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                debugLog(MODULE_NAME, f"Processing Category CREATE for {entity_id}", details={
                    "payload": payload.model_dump() if isinstance(payload, CategoryPayload) else payload,
                    "incoming_updated_at": incoming_updated_at,
                    "normalized_incoming_updated_at": normalized_incoming_updated_at
                })

                try:
                    existing_category = crud_category.get_category(db=db, category_id=entity_id)
                    if existing_category:  # Treat as update if ID already exists
                        normalized_db_updated_at = normalize_datetime_for_comparison(existing_category.updatedAt)
                        debugLog(MODULE_NAME, f"Category {entity_id} already exists, treating CREATE as UPDATE", details={
                            "db_updated_at": existing_category.updatedAt,
                            "normalized_db_updated_at": normalized_db_updated_at,
                            "incoming_updated_at": incoming_updated_at,
                            "normalized_incoming_updated_at": normalized_incoming_updated_at
                        })

                        if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                            updated_category = crud_category.update_category(db=db, db_category=existing_category, category_in=payload)
                            infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Category {entity_id}", details=payload.model_dump())
                            notification_data = CategoryPayload.model_validate(updated_category)
                        else:
                            infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Category {entity_id}", details=payload.model_dump())
                            notification_data = CategoryPayload.model_validate(existing_category)
                            authoritative_data_used = True
                    else:
                        if isinstance(payload, CategoryPayload):
                            debugLog(MODULE_NAME, f"Creating new Category {entity_id}")
                            new_category = crud_category.create_category(db=db, category_in=payload)
                            infoLog(MODULE_NAME, f"Created Category {entity_id}", details=payload.model_dump())
                            notification_data = CategoryPayload.model_validate(new_category)
                        else:
                            error_msg = "Payload mismatch for Category CREATE"
                            errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                            return False, error_msg

                except Exception as category_create_error:
                    error_msg = f"Specific error during Category CREATE {entity_id}: {str(category_create_error)}"
                    errorLog(MODULE_NAME, error_msg, details={
                        "payload": payload.model_dump() if isinstance(payload, CategoryPayload) else payload,
                        "error": str(category_create_error),
                        "error_type": type(category_create_error).__name__
                    })
                    raise category_create_error  # Re-raise to be caught by outer exception handler

            elif operation_type == SyncOperationType.UPDATE:
                if not isinstance(payload, CategoryPayload):
                    error_msg = "Invalid payload type for Category UPDATE"
                    errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                    return False, error_msg

                debugLog(MODULE_NAME, f"Processing Category UPDATE for {entity_id}", details={
                    "payload": payload.model_dump(),
                    "incoming_updated_at": incoming_updated_at,
                    "normalized_incoming_updated_at": normalized_incoming_updated_at
                })

                try:
                    db_category = crud_category.get_category(db=db, category_id=entity_id)
                    if db_category:
                        normalized_db_updated_at = normalize_datetime_for_comparison(db_category.updatedAt)
                        lww_comparison = normalized_incoming_updated_at > normalized_db_updated_at if (normalized_incoming_updated_at and normalized_db_updated_at) else "no_comparison"

                        debugLog(MODULE_NAME, f"Found existing Category {entity_id}", details={
                            "db_updated_at": db_category.updatedAt,
                            "normalized_db_updated_at": normalized_db_updated_at,
                            "incoming_updated_at": incoming_updated_at,
                            "normalized_incoming_updated_at": normalized_incoming_updated_at,
                            "lww_comparison": lww_comparison
                        })

                        if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                            debugLog(MODULE_NAME, f"Attempting Category UPDATE for {entity_id} (LWW win)")
                            updated_category = crud_category.update_category(db=db, db_category=db_category, category_in=payload)
                            infoLog(MODULE_NAME, f"Updated Category {entity_id} (LWW win)", details=payload.model_dump())
                            notification_data = CategoryPayload.model_validate(updated_category)
                        else:
                            infoLog(MODULE_NAME, f"Skipped Category UPDATE {entity_id} (LWW loss/equal or no timestamp)", details=payload.model_dump())
                            notification_data = CategoryPayload.model_validate(db_category)
                            authoritative_data_used = True
                    else:
                        debugLog(MODULE_NAME, f"Category {entity_id} not found, creating during UPDATE (upsert)")
                        new_category = crud_category.create_category(db=db, category_in=payload)
                        infoLog(MODULE_NAME, f"Created Category {entity_id} during UPDATE (upsert)", details=payload.model_dump())
                        notification_data = CategoryPayload.model_validate(new_category)

                except Exception as category_update_error:
                    error_msg = f"Specific error during Category UPDATE {entity_id}: {str(category_update_error)}"
                    errorLog(MODULE_NAME, error_msg, details={
                        "payload": payload.model_dump(),
                        "error": str(category_update_error),
                        "error_type": type(category_update_error).__name__
                    })
                    raise category_update_error  # Re-raise to be caught by outer exception handler

            elif operation_type == SyncOperationType.DELETE:
                debugLog(MODULE_NAME, f"Processing Category DELETE for {entity_id}")

                try:
                    deleted_category = crud_category.delete_category(db=db, category_id=entity_id)
                    if deleted_category:
                        infoLog(MODULE_NAME, f"Deleted Category {entity_id}")
                        notification_data = DeletePayload(id=entity_id)
                    else:
                        infoLog(MODULE_NAME, f"Category {entity_id} not found for DELETE")
                        notification_data = DeletePayload(id=entity_id)
                        authoritative_data_used = True

                except Exception as category_delete_error:
                    error_msg = f"Specific error during Category DELETE {entity_id}: {str(category_delete_error)}"
                    errorLog(MODULE_NAME, error_msg, details={
                        "entity_id": entity_id,
                        "error": str(category_delete_error),
                        "error_type": type(category_delete_error).__name__
                    })
                    raise category_delete_error  # Re-raise to be caught by outer exception handler

        elif entity_type == EntityType.CATEGORY_GROUP:
            if not isinstance(payload, (CategoryGroupPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for CategoryGroup operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_group = crud_category_group.get_category_group(db=db, category_group_id=entity_id)
                if existing_group:  # Treat as update
                    if incoming_updated_at and existing_group.updatedAt and incoming_updated_at > existing_group.updatedAt:
                        updated_group = crud_category_group.update_category_group(db=db, db_category_group=existing_group, category_group_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for CategoryGroup {entity_id}", details=payload)
                        notification_data = CategoryGroupPayload.model_validate(updated_group)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for CategoryGroup {entity_id}", details=payload)
                        notification_data = CategoryGroupPayload.model_validate(existing_group)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, CategoryGroupPayload):
                        new_group = crud_category_group.create_category_group(db=db, category_group_in=payload)
                        infoLog(MODULE_NAME, f"Created CategoryGroup {entity_id}", details=payload)
                        notification_data = CategoryGroupPayload.model_validate(new_group)
                    else:
                        error_msg = "Payload mismatch for CategoryGroup CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                if not isinstance(payload, CategoryGroupPayload):
                    error_msg = "Invalid payload type for CategoryGroup UPDATE"
                    errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                    return False, error_msg
                db_category_group = crud_category_group.get_category_group(db=db, category_group_id=entity_id)
                if db_category_group:
                    if incoming_updated_at and db_category_group.updatedAt and incoming_updated_at > db_category_group.updatedAt:
                        updated_group = crud_category_group.update_category_group(db=db, db_category_group=db_category_group, category_group_in=payload)
                        infoLog(MODULE_NAME, f"Updated CategoryGroup {entity_id} (LWW win)", details=payload)
                        notification_data = CategoryGroupPayload.model_validate(updated_group)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CategoryGroup UPDATE {entity_id} (LWW loss/equal or no timestamp)", details=payload)
                        notification_data = CategoryGroupPayload.model_validate(db_category_group)
                        authoritative_data_used = True
                else:
                    new_group = crud_category_group.create_category_group(db=db, category_group_in=payload)
                    infoLog(MODULE_NAME, f"Created CategoryGroup {entity_id} during UPDATE (upsert)", details=payload)
                    notification_data = CategoryGroupPayload.model_validate(new_group)

            elif operation_type == SyncOperationType.DELETE:
                deleted_group = crud_category_group.delete_category_group(db=db, category_group_id=entity_id)
                if deleted_group:
                    infoLog(MODULE_NAME, f"Deleted CategoryGroup {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"CategoryGroup {entity_id} not found for DELETE")
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True

        elif entity_type == EntityType.RECIPIENT:
            if not isinstance(payload, (RecipientPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Recipient operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_recipient = crud_recipient.get_recipient(db=db, recipient_id=entity_id)
                if existing_recipient:  # Treat as update if ID already exists
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_recipient.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_recipient = crud_recipient.update_recipient(db=db, db_recipient=existing_recipient, recipient_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Recipient {entity_id}", details=payload)
                        notification_data = RecipientPayload.model_validate(updated_recipient)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Recipient {entity_id}", details=payload)
                        notification_data = RecipientPayload.model_validate(existing_recipient)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, RecipientPayload):
                        new_recipient = crud_recipient.create_recipient(db=db, recipient_in=payload)
                        infoLog(MODULE_NAME, f"Created Recipient {entity_id}", details=payload)
                        notification_data = RecipientPayload.model_validate(new_recipient)
                    else:
                        error_msg = "Payload mismatch for Recipient CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                db_recipient = crud_recipient.get_recipient(db=db, recipient_id=entity_id)
                if db_recipient:
                    normalized_db_updated_at = normalize_datetime_for_comparison(db_recipient.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_recipient = crud_recipient.update_recipient(db=db, db_recipient=db_recipient, recipient_in=payload)
                        infoLog(MODULE_NAME, f"Applied Recipient UPDATE {entity_id} (LWW win)", details=payload)
                        notification_data = RecipientPayload.model_validate(updated_recipient)
                    else:
                        infoLog(MODULE_NAME, f"Skipped Recipient UPDATE {entity_id} (LWW loss/equal or no timestamp)", details=payload)
                        notification_data = RecipientPayload.model_validate(db_recipient)
                        authoritative_data_used = True
                else:
                    new_recipient = crud_recipient.create_recipient(db=db, recipient_in=payload)
                    infoLog(MODULE_NAME, f"Created Recipient {entity_id} during UPDATE (upsert)", details=payload)
                    notification_data = RecipientPayload.model_validate(new_recipient)

            elif operation_type == SyncOperationType.DELETE:
                deleted_recipient = crud_recipient.delete_recipient(db=db, recipient_id=entity_id)
                if deleted_recipient:
                    infoLog(MODULE_NAME, f"Deleted Recipient {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"Recipient {entity_id} not found for DELETE")
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True

        elif entity_type == EntityType.TAG:
            if not isinstance(payload, (TagPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Tag operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_tag = crud_tag.get_tag(db=db, tag_id=entity_id)
                if existing_tag:  # Treat as update if ID already exists
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_tag.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_tag = crud_tag.update_tag(db=db, db_tag=existing_tag, tag_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Tag {entity_id}", details=payload)
                        notification_data = TagPayload.model_validate(updated_tag)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Tag {entity_id}", details=payload)
                        notification_data = TagPayload.model_validate(existing_tag)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, TagPayload):
                        new_tag = crud_tag.create_tag(db=db, tag_in=payload)
                        infoLog(MODULE_NAME, f"Created Tag {entity_id}", details=payload)
                        notification_data = TagPayload.model_validate(new_tag)
                    else:
                        error_msg = "Payload mismatch for Tag CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                db_tag = crud_tag.get_tag(db=db, tag_id=entity_id)
                if db_tag:
                    normalized_db_updated_at = normalize_datetime_for_comparison(db_tag.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_tag = crud_tag.update_tag(db=db, db_tag=db_tag, tag_in=payload)
                        infoLog(MODULE_NAME, f"Applied Tag UPDATE {entity_id} (LWW win)", details=payload)
                        notification_data = TagPayload.model_validate(updated_tag)
                    else:
                        infoLog(MODULE_NAME, f"Skipped Tag UPDATE {entity_id} (LWW loss/equal or no timestamp)", details=payload)
                        notification_data = TagPayload.model_validate(db_tag)
                        authoritative_data_used = True
                else:
                    new_tag = crud_tag.create_tag(db=db, tag_in=payload)
                    infoLog(MODULE_NAME, f"Created Tag {entity_id} during UPDATE (upsert)", details=payload)
                    notification_data = TagPayload.model_validate(new_tag)

            elif operation_type == SyncOperationType.DELETE:
                deleted_tag = crud_tag.delete_tag(db=db, tag_id=entity_id)
                if deleted_tag:
                    infoLog(MODULE_NAME, f"Deleted Tag {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"Tag {entity_id} not found for DELETE")
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True

        elif entity_type == EntityType.AUTOMATION_RULE:
            if not isinstance(payload, (AutomationRulePayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for AutomationRule operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_rule = crud_automation_rule.get_automation_rule(db=db, automation_rule_id=entity_id)
                if existing_rule:  # Treat as update if ID already exists
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_rule.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_rule = crud_automation_rule.update_automation_rule(db=db, db_automation_rule=existing_rule, automation_rule_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for AutomationRule {entity_id}", details=payload)
                        notification_data = AutomationRulePayload.model_validate(updated_rule)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for AutomationRule {entity_id}", details=payload)
                        notification_data = AutomationRulePayload.model_validate(existing_rule)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, AutomationRulePayload):
                        new_rule = crud_automation_rule.create_automation_rule(db=db, automation_rule_in=payload)
                        infoLog(MODULE_NAME, f"Created AutomationRule {entity_id}", details=payload)
                        notification_data = AutomationRulePayload.model_validate(new_rule)
                    else:
                        error_msg = "Payload mismatch for AutomationRule CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                existing_rule = crud_automation_rule.get_automation_rule(db=db, automation_rule_id=entity_id)
                if existing_rule:
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_rule.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_rule = crud_automation_rule.update_automation_rule(db=db, db_automation_rule=existing_rule, automation_rule_in=payload)
                        infoLog(MODULE_NAME, f"Applied UPDATE (LWW win) for AutomationRule {entity_id}", details=payload)
                        notification_data = AutomationRulePayload.model_validate(updated_rule)
                    else:
                        infoLog(MODULE_NAME, f"Skipped UPDATE (LWW loss/equal) for AutomationRule {entity_id}", details=payload)
                        notification_data = AutomationRulePayload.model_validate(existing_rule)
                        authoritative_data_used = True
                else:
                    infoLog(MODULE_NAME, f"AutomationRule {entity_id} not found for UPDATE")
                    return False, "automation_rule_not_found"

            elif operation_type == SyncOperationType.DELETE:
                existing_rule = crud_automation_rule.get_automation_rule(db=db, automation_rule_id=entity_id)
                if existing_rule:
                    crud_automation_rule.delete_automation_rule(db=db, automation_rule_id=entity_id)
                    infoLog(MODULE_NAME, f"Deleted AutomationRule {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"AutomationRule {entity_id} not found for DELETE")
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True

        elif entity_type == EntityType.PLANNING_TRANSACTION:
            if not isinstance(payload, (PlanningTransactionPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for PlanningTransaction operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_planning_transaction = crud_planning_transaction.get_planning_transaction(db=db, planning_transaction_id=entity_id)
                if existing_planning_transaction:  # Treat as update if ID already exists
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_planning_transaction.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_planning_transaction = crud_planning_transaction.update_planning_transaction(db=db, db_planning_transaction=existing_planning_transaction, planning_transaction_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for PlanningTransaction {entity_id}", details=payload)
                        notification_data = PlanningTransactionPayload.model_validate(updated_planning_transaction)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for PlanningTransaction {entity_id}", details=payload)
                        notification_data = PlanningTransactionPayload.model_validate(existing_planning_transaction)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, PlanningTransactionPayload):
                        new_planning_transaction = crud_planning_transaction.create_planning_transaction(db=db, planning_transaction_in=payload)
                        infoLog(MODULE_NAME, f"Created PlanningTransaction {entity_id}", details=payload)
                        notification_data = PlanningTransactionPayload.model_validate(new_planning_transaction)
                    else:
                        error_msg = "Payload mismatch for PlanningTransaction CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                existing_planning_transaction = crud_planning_transaction.get_planning_transaction(db=db, planning_transaction_id=entity_id)
                if existing_planning_transaction:
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_planning_transaction.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_planning_transaction = crud_planning_transaction.update_planning_transaction(db=db, db_planning_transaction=existing_planning_transaction, planning_transaction_in=payload)
                        infoLog(MODULE_NAME, f"Applied UPDATE (LWW win) for PlanningTransaction {entity_id}", details=payload)
                        notification_data = PlanningTransactionPayload.model_validate(updated_planning_transaction)
                    else:
                        infoLog(MODULE_NAME, f"Skipped UPDATE (LWW loss/equal) for PlanningTransaction {entity_id}", details=payload)
                        notification_data = PlanningTransactionPayload.model_validate(existing_planning_transaction)
                        authoritative_data_used = True
                else:
                    infoLog(MODULE_NAME, f"PlanningTransaction {entity_id} not found for UPDATE")
                    return False, "planning_transaction_not_found"

            elif operation_type == SyncOperationType.DELETE:
                existing_planning_transaction = crud_planning_transaction.get_planning_transaction(db=db, planning_transaction_id=entity_id)
                if existing_planning_transaction:
                    crud_planning_transaction.delete_planning_transaction(db=db, planning_transaction_id=entity_id)
                    infoLog(MODULE_NAME, f"Deleted PlanningTransaction {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"PlanningTransaction {entity_id} not found for DELETE")
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True

        elif entity_type == EntityType.TRANSACTION:
            if not isinstance(payload, (TransactionPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Transaction operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_transaction = crud_transaction.get_transaction(db=db, id=entity_id)
                if existing_transaction:
                    # LWW: Compare timestamps
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_transaction.updatedAt)
                    if isinstance(payload, TransactionPayload) and normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_transaction = crud_transaction.update_transaction(db=db, db_obj=existing_transaction, obj_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Transaction {entity_id}", details=payload)
                        notification_data = TransactionPayload.model_validate(updated_transaction)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Transaction {entity_id}", details=payload)
                        notification_data = TransactionPayload.model_validate(existing_transaction)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, TransactionPayload):
                        new_transaction = crud_transaction.create_transaction(db=db, obj_in=payload, tenant_id=entry.tenantId)
                        infoLog(MODULE_NAME, f"Created Transaction {entity_id}", details=payload)
                        notification_data = TransactionPayload.model_validate(new_transaction)
                    else:
                        error_msg = "Payload mismatch for Transaction CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                existing_transaction = crud_transaction.get_transaction(db=db, id=entity_id)
                if existing_transaction and isinstance(payload, TransactionPayload):
                    # LWW: Compare timestamps
                    normalized_db_updated_at = normalize_datetime_for_comparison(existing_transaction.updatedAt)
                    if normalized_incoming_updated_at and normalized_db_updated_at and normalized_incoming_updated_at > normalized_db_updated_at:
                        updated_transaction = crud_transaction.update_transaction(db=db, db_obj=existing_transaction, obj_in=payload)
                        infoLog(MODULE_NAME, f"Applied UPDATE (LWW win) for Transaction {entity_id}", details=payload)
                        notification_data = TransactionPayload.model_validate(updated_transaction)
                    else:
                        infoLog(MODULE_NAME, f"Skipped UPDATE (LWW loss/equal) for Transaction {entity_id}", details=payload)
                        notification_data = TransactionPayload.model_validate(existing_transaction)
                        authoritative_data_used = True
                else:
                    infoLog(MODULE_NAME, f"Transaction {entity_id} not found for UPDATE")
                    return False, "transaction_not_found"

            elif operation_type == SyncOperationType.DELETE:
                existing_transaction = crud_transaction.get_transaction(db=db, id=entity_id)
                if existing_transaction:
                    crud_transaction.delete_transaction(db=db, id=entity_id)
                    infoLog(MODULE_NAME, f"Deleted Transaction {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"Transaction {entity_id} not found for DELETE")
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
                message.model_dump(mode='json'),
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
    except RuntimeError as e:
        if "Unexpected ASGI message 'websocket.send'" in str(e):
            error_msg = f"WebSocket state error processing sync entry {entry.id} for tenant {entry.tenantId}: {e}"
            warnLog(MODULE_NAME, error_msg, details={"entry": entry.model_dump(), "error": str(e)})
            return False, "websocket_state_error"
        else:
            error_msg = f"Unhandled RuntimeError processing sync entry {entry.id} for tenant {entry.tenantId}: {e}"
            errorLog(MODULE_NAME, error_msg, details={"entry": entry.model_dump(), "error": str(e)})
            return False, "generic_runtime_error"
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
        categories_db = crud_category.get_categories(db=db)
        category_groups_db = crud_category_group.get_category_groups(db=db)
        recipients_db = crud_recipient.get_recipients(db=db)
        tags_db = crud_tag.get_tags(db=db)
        automation_rules_db = crud_automation_rule.get_automation_rules(db=db)
        planning_transactions_db = crud_planning_transaction.get_planning_transactions(db=db)
        transactions_db = crud_transaction.get_multi(db=db)

        accounts_payload = [AccountPayload.model_validate(acc) for acc in accounts_db]
        account_groups_payload = [AccountGroupPayload.model_validate(ag) for ag in account_groups_db]
        categories_payload = [CategoryPayload.model_validate(cat) for cat in categories_db]
        category_groups_payload = [CategoryGroupPayload.model_validate(cg) for cg in category_groups_db]
        recipients_payload = [RecipientPayload.model_validate(rec) for rec in recipients_db]
        tags_payload = [TagPayload.model_validate(tag) for tag in tags_db]
        automation_rules_payload = [AutomationRulePayload.model_validate(rule) for rule in automation_rules_db]
        planning_transactions_payload = [PlanningTransactionPayload.model_validate(pt) for pt in planning_transactions_db]
        transactions_payload = [TransactionPayload.model_validate(tx) for tx in transactions_db]

        initial_data = InitialDataPayload(
            accounts=accounts_payload,
            account_groups=account_groups_payload,
            categories=categories_payload,
            category_groups=category_groups_payload,
            recipients=recipients_payload,
            tags=tags_payload,
            automation_rules=automation_rules_payload,
            planning_transactions=planning_transactions_payload,
            transactions=transactions_payload
        )
        infoLog(MODULE_NAME, f"Successfully retrieved initial data for tenant {tenant_id}. Accounts: {len(accounts_payload)}, AccountGroups: {len(account_groups_payload)}, Categories: {len(categories_payload)}, CategoryGroups: {len(category_groups_payload)}, Recipients: {len(recipients_payload)}, Tags: {len(tags_payload)}, AutomationRules: {len(automation_rules_payload)}, PlanningTransactions: {len(planning_transactions_payload)}, Transactions: {len(transactions_payload)}")
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


def calculate_entity_checksum(entity_data: dict) -> str:
    """Berechnet eine Checksumme für Entitätsdaten zur Konfliktserkennung."""
    # Sortiere die Daten für konsistente Checksummen
    sorted_data = json.dumps(entity_data, sort_keys=True, default=str)
    return hashlib.md5(sorted_data.encode()).hexdigest()


async def get_data_status_for_tenant(tenant_id: str, entity_types: Optional[list[EntityType]] = None) -> Optional[DataStatusResponseMessage]:
    """Erstellt eine Datenstatusantwort mit Checksummen für Konfliktserkennung."""
    debugLog(MODULE_NAME, f"Getting data status for tenant {tenant_id}", details={"entity_types": entity_types})

    db: Optional[Session] = None
    try:
        db = get_tenant_db_session(tenant_id)
        if db is None:
            error_msg = f"Could not get DB session for tenant {tenant_id} during data status fetch."
            errorLog(MODULE_NAME, error_msg)
            return None

        entity_checksums = {}
        current_time = int(time.time())

        # Standardmäßig alle Entitätstypen verarbeiten, wenn keine spezifiziert
        if entity_types is None:
            entity_types = [EntityType.ACCOUNT, EntityType.ACCOUNT_GROUP, EntityType.CATEGORY, EntityType.CATEGORY_GROUP]

        for entity_type in entity_types:
            checksums = []

            if entity_type == EntityType.ACCOUNT:
                accounts_db = crud_account.get_accounts(db=db)
                for account in accounts_db:
                    account_data = {
                        'id': account.id,
                        'name': account.name,
                        'description': account.description,
                        'note': account.note,
                        'accountType': account.accountType,
                        'isActive': account.isActive,
                        'isOfflineBudget': account.isOfflineBudget,
                        'accountGroupId': account.accountGroupId,
                        'sortOrder': account.sortOrder,
                        'iban': account.iban,
                        'balance': float(account.balance) if account.balance else 0.0,
                        'creditLimit': float(account.creditLimit) if account.creditLimit else None,
                        'offset': account.offset,
                        'logo_path': account.logo_path,
                        'updated_at': account.updatedAt.isoformat() if account.updatedAt else None
                    }
                    checksum = calculate_entity_checksum(account_data)
                    last_modified = int(account.updatedAt.timestamp()) if account.updatedAt else 0

                    checksums.append(EntityChecksum(
                        entity_id=account.id,
                        checksum=checksum,
                        last_modified=last_modified
                    ))

            elif entity_type == EntityType.ACCOUNT_GROUP:
                account_groups_db = crud_account_group.get_account_groups(db=db)
                for group in account_groups_db:
                    group_data = {
                        'id': group.id,
                        'name': group.name,
                        'sortOrder': group.sortOrder,
                        'logo_path': group.logo_path,
                        'updated_at': group.updatedAt.isoformat() if group.updatedAt else None
                    }
                    checksum = calculate_entity_checksum(group_data)
                    last_modified = int(group.updatedAt.timestamp()) if group.updatedAt else 0

                    checksums.append(EntityChecksum(
                        entity_id=group.id,
                        checksum=checksum,
                        last_modified=last_modified
                    ))

            elif entity_type == EntityType.CATEGORY:
                categories_db = crud_category.get_categories(db=db)
                for category in categories_db:
                    category_data = {
                        'id': category.id,
                        'name': category.name,
                        'icon': category.icon,
                        'budgeted': float(category.budgeted) if category.budgeted else 0.0,
                        'activity': float(category.activity) if category.activity else 0.0,
                        'available': float(category.available) if category.available else 0.0,
                        'isIncomeCategory': category.isIncomeCategory,
                        'isHidden': category.isHidden,
                        'isActive': category.isActive,
                        'sortOrder': category.sortOrder,
                        'categoryGroupId': category.categoryGroupId,
                        'parentCategoryId': category.parentCategoryId,
                        'isSavingsGoal': category.isSavingsGoal,
                        'updated_at': category.updatedAt.isoformat() if category.updatedAt else None
                    }
                    checksum = calculate_entity_checksum(category_data)
                    last_modified = int(category.updatedAt.timestamp()) if category.updatedAt else 0

                    checksums.append(EntityChecksum(
                        entity_id=category.id,
                        checksum=checksum,
                        last_modified=last_modified
                    ))

            elif entity_type == EntityType.CATEGORY_GROUP:
                category_groups_db = crud_category_group.get_category_groups(db=db)
                for group in category_groups_db:
                    group_data = {
                        'id': group.id,
                        'name': group.name,
                        'sortOrder': group.sortOrder,
                        'isIncomeGroup': group.isIncomeGroup,
                        'updated_at': group.updatedAt.isoformat() if group.updatedAt else None
                    }
                    checksum = calculate_entity_checksum(group_data)
                    last_modified = int(group.updatedAt.timestamp()) if group.updatedAt else 0

                    checksums.append(EntityChecksum(
                        entity_id=group.id,
                        checksum=checksum,
                        last_modified=last_modified
                    ))

            elif entity_type == EntityType.RECIPIENT:
                recipients_db = crud_recipient.get_recipients(db=db)
                for recipient in recipients_db:
                    recipient_data = {
                        'id': recipient.id,
                        'name': recipient.name,
                        'defaultCategoryId': recipient.defaultCategoryId,
                        'note': recipient.note,
                        'updated_at': recipient.updatedAt.isoformat() if recipient.updatedAt else None
                    }
                    checksum = calculate_entity_checksum(recipient_data)
                    last_modified = int(recipient.updatedAt.timestamp()) if recipient.updatedAt else 0

                    checksums.append(EntityChecksum(
                        entity_id=recipient.id,
                        checksum=checksum,
                        last_modified=last_modified
                    ))

            elif entity_type == EntityType.TAG:
                tags_db = crud_tag.get_tags(db=db)
                for tag in tags_db:
                    tag_data = {
                        'id': tag.id,
                        'name': tag.name,
                        'parentTagId': tag.parentTagId,
                        'color': tag.color,
                        'icon': tag.icon,
                        'updated_at': tag.updatedAt.isoformat() if tag.updatedAt else None
                    }
                    checksum = calculate_entity_checksum(tag_data)
                    last_modified = int(tag.updatedAt.timestamp()) if tag.updatedAt else 0

                    checksums.append(EntityChecksum(
                        entity_id=tag.id,
                        checksum=checksum,
                        last_modified=last_modified
                    ))

            entity_checksums[entity_type.value] = checksums

        response = DataStatusResponseMessage(
            tenant_id=tenant_id,
            entity_checksums=entity_checksums,
            last_sync_time=current_time,  # TODO: Implementiere echte letzte Sync-Zeit
            server_time=current_time
        )

        infoLog(MODULE_NAME, f"Successfully created data status response for tenant {tenant_id}",
                details={"entity_types": [et.value for et in entity_types], "total_entities": sum(len(checksums) for checksums in entity_checksums.values())})
        return response

    except sqlite3.OperationalError as oe:
        error_msg = f"Database operational error getting data status for tenant {tenant_id}: {str(oe)}"
        error_reason = "database_operational_error"
        if "no such table" in str(oe).lower():
            error_reason = "table_not_found"
        errorLog(MODULE_NAME, error_msg, details={"tenant_id": tenant_id, "error": str(oe), "reason": error_reason})
        return None
    except Exception as e:
        error_msg = f"Generic error getting data status for tenant {tenant_id}: {str(e)}"
        errorLog(MODULE_NAME, error_msg, details={"tenant_id": tenant_id, "error": str(e)})
        return None
    finally:
        if db:
            db.close()


async def detect_conflicts(tenant_id: str, client_checksums: dict) -> dict:
    """Erkennt Konflikte zwischen Client- und Server-Daten basierend auf Checksummen."""
    debugLog(MODULE_NAME, f"Detecting conflicts for tenant {tenant_id}")

    server_status = await get_data_status_for_tenant(tenant_id)
    if not server_status:
        errorLog(MODULE_NAME, f"Could not get server status for conflict detection for tenant {tenant_id}")
        return {"conflicts": [], "local_only": [], "server_only": []}

    conflicts = []
    local_only = []
    server_only = []

    # Vergleiche Client- und Server-Checksummen
    for entity_type, client_entities in client_checksums.items():
        server_entities = server_status.entity_checksums.get(entity_type, [])
        server_entity_map = {entity.entity_id: entity for entity in server_entities}
        client_entity_map = {entity['entity_id']: entity for entity in client_entities}

        # Finde Konflikte und nur-lokale Entitäten
        for entity_id, client_entity in client_entity_map.items():
            if entity_id in server_entity_map:
                server_entity = server_entity_map[entity_id]
                if client_entity['checksum'] != server_entity.checksum:
                    conflicts.append({
                        'entity_type': entity_type,
                        'entity_id': entity_id,
                        'local_checksum': client_entity['checksum'],
                        'server_checksum': server_entity.checksum,
                        'local_last_modified': client_entity.get('last_modified', 0),
                        'server_last_modified': server_entity.last_modified
                    })
            else:
                local_only.append({
                    'entity_type': entity_type,
                    'entity_id': entity_id
                })

        # Finde nur-Server-Entitäten
        for entity_id, server_entity in server_entity_map.items():
            if entity_id not in client_entity_map:
                server_only.append({
                    'entity_type': entity_type,
                    'entity_id': entity_id
                })

    result = {
        "conflicts": conflicts,
        "local_only": local_only,
        "server_only": server_only
    }

    infoLog(MODULE_NAME, f"Conflict detection completed for tenant {tenant_id}",
            details={"conflicts": len(conflicts), "local_only": len(local_only), "server_only": len(server_only)})

    return result

async def process_sync_entries_staged(entries: list[SyncQueueEntry], source_websocket: Optional[WebSocket] = None) -> tuple[list[str], list[str]]:
    """
    Processes sync entries in two stages to handle dependencies:
    Stage 1: Recipients, Categories, CategoryGroups, Accounts, AccountGroups, Tags, AutomationRules
    Stage 2: Transactions, PlanningTransactions

    Returns: (successful_entry_ids, failed_entry_ids)
    """
    debugLog(MODULE_NAME, f"Starting staged sync processing for {len(entries)} entries")

    # Separate entries by stage
    stage1_entities = {EntityType.RECIPIENT, EntityType.CATEGORY, EntityType.CATEGORY_GROUP,
                      EntityType.ACCOUNT, EntityType.ACCOUNT_GROUP, EntityType.TAG, EntityType.AUTOMATION_RULE}
    stage2_entities = {EntityType.TRANSACTION, EntityType.PLANNING_TRANSACTION}

    stage1_entries = [entry for entry in entries if entry.entityType in stage1_entities]
    stage2_entries = [entry for entry in entries if entry.entityType in stage2_entities]
    other_entries = [entry for entry in entries if entry.entityType not in stage1_entities and entry.entityType not in stage2_entities]

    successful_ids = []
    failed_ids = []

    # Stage 1: Process master data first
    if stage1_entries:
        infoLog(MODULE_NAME, f"Stage 1: Processing {len(stage1_entries)} master data entries")
        for entry in stage1_entries:
            try:
                success, reason = await process_sync_entry(entry, source_websocket)
                if success:
                    successful_ids.append(entry.id)
                    debugLog(MODULE_NAME, f"Stage 1 success: {entry.entityType.value} {entry.entityId}")
                else:
                    failed_ids.append(entry.id)
                    errorLog(MODULE_NAME, f"Stage 1 failed: {entry.entityType.value} {entry.entityId} - {reason}")
            except Exception as e:
                failed_ids.append(entry.id)
                errorLog(MODULE_NAME, f"Stage 1 exception: {entry.entityType.value} {entry.entityId} - {str(e)}")

    # Stage 2: Process transactions after master data
    if stage2_entries:
        infoLog(MODULE_NAME, f"Stage 2: Processing {len(stage2_entries)} transaction entries")
        for entry in stage2_entries:
            try:
                success, reason = await process_sync_entry(entry, source_websocket)
                if success:
                    successful_ids.append(entry.id)
                    debugLog(MODULE_NAME, f"Stage 2 success: {entry.entityType.value} {entry.entityId}")
                else:
                    failed_ids.append(entry.id)
                    errorLog(MODULE_NAME, f"Stage 2 failed: {entry.entityType.value} {entry.entityId} - {reason}")
            except Exception as e:
                failed_ids.append(entry.id)
                errorLog(MODULE_NAME, f"Stage 2 exception: {entry.entityType.value} {entry.entityId} - {str(e)}")

    # Process any other entities
    if other_entries:
        infoLog(MODULE_NAME, f"Processing {len(other_entries)} other entries")
        for entry in other_entries:
            try:
                success, reason = await process_sync_entry(entry, source_websocket)
                if success:
                    successful_ids.append(entry.id)
                else:
                    failed_ids.append(entry.id)
            except Exception as e:
                failed_ids.append(entry.id)
                errorLog(MODULE_NAME, f"Other entry exception: {entry.entityType.value} {entry.entityId} - {str(e)}")

    infoLog(MODULE_NAME, f"Staged sync completed: {len(successful_ids)} successful, {len(failed_ids)} failed")
    return successful_ids, failed_ids


# In-memory queue storage (in production, use Redis or database)
_sync_queues: Dict[str, List[SyncQueueEntry]] = {}
_failed_entries: Dict[str, List[dict]] = {}  # tenant_id -> list of failed entry info


def add_to_sync_queue(tenant_id: str, entry: SyncQueueEntry):
    """Add a sync entry to the tenant's queue."""
    if tenant_id not in _sync_queues:
        _sync_queues[tenant_id] = []
    _sync_queues[tenant_id].append(entry)
    debugLog(MODULE_NAME, f"Added entry {entry.id} to sync queue for tenant {tenant_id}")


def get_pending_sync_entries_for_tenant(tenant_id: str) -> List[SyncQueueEntry]:
    """Get all pending sync entries for a tenant."""
    return _sync_queues.get(tenant_id, [])


def remove_from_sync_queue(tenant_id: str, entry_id: str):
    """Remove a successfully processed entry from the queue."""
    if tenant_id in _sync_queues:
        _sync_queues[tenant_id] = [entry for entry in _sync_queues[tenant_id] if entry.id != entry_id]


def add_failed_entry(tenant_id: str, entry_id: str, error: str, retry_count: int = 0):
    """Add a failed entry to the failed entries tracking."""
    if tenant_id not in _failed_entries:
        _failed_entries[tenant_id] = []

    failed_info = {
        "entry_id": entry_id,
        "error": error,
        "retry_count": retry_count,
        "last_attempt": int(time.time()),
        "next_retry": int(time.time()) + (60 * (2 ** retry_count))  # Exponential backoff
    }
    _failed_entries[tenant_id].append(failed_info)


def get_retryable_entries(tenant_id: str) -> List[str]:
    """Get entry IDs that are ready for retry."""
    if tenant_id not in _failed_entries:
        return []

    current_time = int(time.time())
    retryable = []

    for failed_info in _failed_entries[tenant_id]:
        if (failed_info["retry_count"] < 3 and
            current_time >= failed_info["next_retry"]):
            retryable.append(failed_info["entry_id"])

    return retryable


async def process_sync_queue_for_tenant(tenant_id: str, source_websocket: Optional[WebSocket] = None) -> dict:
    """
    Processes all pending sync entries for a tenant using staged synchronization.
    This function should be called when the frontend requests a full sync or when retrying failed entries.

    Returns: {"processed": int, "successful": int, "failed": int, "failed_entries": list}
    """
    debugLog(MODULE_NAME, f"Processing sync queue for tenant {tenant_id}")

    # Get pending entries from queue
    pending_entries = get_pending_sync_entries_for_tenant(tenant_id)

    if not pending_entries:
        infoLog(MODULE_NAME, f"No pending sync entries for tenant {tenant_id}")
        return {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "failed_entries": []
        }

    # Process entries using staged synchronization
    successful_ids, failed_ids = await process_sync_entries_staged(pending_entries, source_websocket)

    # Update queue state
    for entry_id in successful_ids:
        remove_from_sync_queue(tenant_id, entry_id)

    for entry_id in failed_ids:
        # Find the entry to get error details
        failed_entry = next((e for e in pending_entries if e.id == entry_id), None)
        if failed_entry:
            add_failed_entry(tenant_id, entry_id, "processing_failed")

    result = {
        "processed": len(pending_entries),
        "successful": len(successful_ids),
        "failed": len(failed_ids),
        "failed_entries": failed_ids
    }

    infoLog(MODULE_NAME, f"Queue processing completed for tenant {tenant_id}: {result}")
    return result


async def retry_failed_entries_for_tenant(tenant_id: str, source_websocket: Optional[WebSocket] = None) -> dict:
    """
    Retry failed sync entries that are ready for retry.

    Returns: {"retried": int, "successful": int, "failed": int, "failed_entries": list}
    """
    debugLog(MODULE_NAME, f"Retrying failed entries for tenant {tenant_id}")

    retryable_entry_ids = get_retryable_entries(tenant_id)

    if not retryable_entry_ids:
        debugLog(MODULE_NAME, f"No retryable entries for tenant {tenant_id}")
        return {
            "retried": 0,
            "successful": 0,
            "failed": 0,
            "failed_entries": []
        }

    # Get the actual entries from the queue
    pending_entries = get_pending_sync_entries_for_tenant(tenant_id)
    retry_entries = [entry for entry in pending_entries if entry.id in retryable_entry_ids]

    if not retry_entries:
        debugLog(MODULE_NAME, f"No retry entries found in queue for tenant {tenant_id}")
        return {
            "retried": 0,
            "successful": 0,
            "failed": 0,
            "failed_entries": []
        }

    # Process retry entries using staged synchronization
    successful_ids, failed_ids = await process_sync_entries_staged(retry_entries, source_websocket)

    # Update queue and failed entries state
    for entry_id in successful_ids:
        remove_from_sync_queue(tenant_id, entry_id)
        # Remove from failed entries
        if tenant_id in _failed_entries:
            _failed_entries[tenant_id] = [f for f in _failed_entries[tenant_id] if f["entry_id"] != entry_id]

    for entry_id in failed_ids:
        # Update retry count for failed entries
        if tenant_id in _failed_entries:
            for failed_info in _failed_entries[tenant_id]:
                if failed_info["entry_id"] == entry_id:
                    failed_info["retry_count"] += 1
                    failed_info["last_attempt"] = int(time.time())
                    failed_info["next_retry"] = int(time.time()) + (60 * (2 ** failed_info["retry_count"]))
                    break

    result = {
        "retried": len(retry_entries),
        "successful": len(successful_ids),
        "failed": len(failed_ids),
        "failed_entries": failed_ids
    }

    infoLog(MODULE_NAME, f"Retry processing completed for tenant {tenant_id}: {result}")
    return result


def get_sync_queue_status(tenant_id: str) -> dict:
    """
    Get the current status of the sync queue for a tenant.

    Returns: {"pending_count": int, "failed_count": int, "retryable_count": int}
    """
    pending_entries = get_pending_sync_entries_for_tenant(tenant_id)
    failed_entries = _failed_entries.get(tenant_id, [])
    retryable_entries = get_retryable_entries(tenant_id)

    return {
        "pending_count": len(pending_entries),
        "failed_count": len(failed_entries),
        "retryable_count": len(retryable_entries),
        "has_pending_entries": len(pending_entries) > 0 or len(retryable_entries) > 0
    }


def should_retry_sync_entry(entry: SyncQueueEntry, retry_count: int, last_error: str) -> bool:
    """
    Determines if a sync entry should be retried based on the error type and retry count.
    """
    max_retries = 3

    if retry_count >= max_retries:
        return False

    # Don't retry validation errors
    if "validation_error" in last_error:
        return False

    # Don't retry if entity not found for UPDATE operations
    if "not_found" in last_error and entry.operationType == SyncOperationType.UPDATE:
        return False

    # Retry database errors, websocket errors, and generic processing errors
    retryable_errors = ["database_operational_error", "websocket_state_error", "generic_processing_error"]
    return any(error in last_error for error in retryable_errors)



async def notify_sync_status_change(tenant_id: str, websocket: Optional[WebSocket] = None):
    """
    Notifies the frontend about sync status changes.
    """
    try:
        queue_status = get_sync_queue_status(tenant_id)

        status_message = {
            "type": "sync_status_update",
            "tenant_id": tenant_id,
            "pending_count": queue_status.get("pending_count", 0),
            "failed_count": queue_status.get("failed_count", 0),
            "retryable_count": queue_status.get("retryable_count", 0),
            "has_pending_entries": queue_status.get("has_pending_entries", False),
            "timestamp": int(time.time())
        }

        if websocket:
            # Send to specific websocket
            await websocket_manager_instance.send_personal_json_message(status_message, websocket)
        else:
            # Broadcast to all clients of the tenant
            await websocket_manager_instance.broadcast_json_to_tenant(status_message, tenant_id)

        debugLog(MODULE_NAME, f"Sent sync status update to tenant {tenant_id}", details=status_message)

    except Exception as e:
        errorLog(MODULE_NAME, f"Failed to notify sync status change for tenant {tenant_id}: {str(e)}")


async def check_and_retry_pending_entries():
    """
    Background task that periodically checks for retryable entries and processes them.
    This should be called periodically (e.g., every 5 minutes) by a scheduler.
    """
    debugLog(MODULE_NAME, "Checking for retryable entries across all tenants")

    for tenant_id in _sync_queues.keys():
        try:
            retryable_entries = get_retryable_entries(tenant_id)

            if retryable_entries:
                infoLog(MODULE_NAME, f"Found {len(retryable_entries)} retryable entries for tenant {tenant_id}")

                # Process retryable entries
                retry_result = await retry_failed_entries_for_tenant(tenant_id)

                # Notify frontend about status change
                await notify_sync_status_change(tenant_id)

                infoLog(MODULE_NAME, f"Retry completed for tenant {tenant_id}: {retry_result}")

        except Exception as e:
            errorLog(MODULE_NAME, f"Error during retry check for tenant {tenant_id}: {str(e)}")


def has_pending_sync_entries(tenant_id: str) -> bool:
    """
    Check if a tenant has pending sync entries that need processing.
    This can be used by the frontend to determine if it should trigger a sync retry.
    """
    queue_status = get_sync_queue_status(tenant_id)
    return queue_status.get("has_pending_entries", False)


async def trigger_cyclic_sync_if_needed(tenant_id: str, websocket: Optional[WebSocket] = None):
    """
    Triggers a cyclic sync retry if there are pending entries.
    This should be called by the frontend when it detects pending entries.
    """
    if not has_pending_sync_entries(tenant_id):
        debugLog(MODULE_NAME, f"No pending entries for tenant {tenant_id}, skipping cyclic sync")
        return {"triggered": False, "reason": "no_pending_entries"}

    infoLog(MODULE_NAME, f"Triggering cyclic sync for tenant {tenant_id}")

    try:
        # First try to retry failed entries
        retry_result = await retry_failed_entries_for_tenant(tenant_id, websocket)

        # Then process any remaining queue entries
        queue_result = await process_sync_queue_for_tenant(tenant_id, websocket)

        # Notify about status change
        await notify_sync_status_change(tenant_id, websocket)

        combined_result = {
            "triggered": True,
            "retry_result": retry_result,
            "queue_result": queue_result,
            "total_processed": retry_result.get("retried", 0) + queue_result.get("processed", 0),
            "total_successful": retry_result.get("successful", 0) + queue_result.get("successful", 0),
            "total_failed": retry_result.get("failed", 0) + queue_result.get("failed", 0)
        }

        infoLog(MODULE_NAME, f"Cyclic sync completed for tenant {tenant_id}: {combined_result}")
        return combined_result

    except Exception as e:
        errorLog(MODULE_NAME, f"Error during cyclic sync for tenant {tenant_id}: {str(e)}")
        return {"triggered": False, "error": str(e)}
