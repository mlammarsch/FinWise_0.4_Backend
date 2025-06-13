from sqlalchemy.orm import Session
from typing import Optional  # Added for Optional WebSocket
from fastapi import WebSocket  # Added for WebSocket type hint
from app.websocket.schemas import (
    SyncQueueEntry, EntityType, SyncOperationType,
    AccountPayload, AccountGroupPayload, CategoryPayload, CategoryGroupPayload, DeletePayload,
    DataUpdateNotificationMessage, ServerEventType, InitialDataPayload,
    DataStatusResponseMessage, EntityChecksum
)
from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal
from app.models.financial_models import TenantBase, Account, AccountGroup, Category, CategoryGroup  # Import all models
from app.crud import crud_account, crud_account_group, crud_category, crud_category_group
from app.utils.logger import infoLog, errorLog, debugLog
from app.websocket.connection_manager import manager as websocket_manager_instance  # Import the global manager
from datetime import datetime  # Import datetime for comparison
import sqlite3  # Import sqlite3 to catch specific operational errors
import hashlib  # Import hashlib for checksum calculation
import json  # Import json for serialization
import time  # Import time for timestamps

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

        notification_data: Optional[AccountPayload | AccountGroupPayload | CategoryPayload | CategoryGroupPayload | DeletePayload] = None
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

        elif entity_type == EntityType.CATEGORY:
            if not isinstance(payload, (CategoryPayload, DeletePayload)) and operation_type != SyncOperationType.DELETE:
                error_msg = "Invalid payload type for Category operation"
                errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                return False, error_msg

            if operation_type == SyncOperationType.CREATE:
                existing_category = crud_category.get_category(db=db, category_id=entity_id)
                if existing_category:  # Treat as update if ID already exists
                    if incoming_updated_at and existing_category.updatedAt and incoming_updated_at > existing_category.updatedAt:
                        updated_category = crud_category.update_category(db=db, db_category=existing_category, category_in=payload)
                        infoLog(MODULE_NAME, f"Applied CREATE as UPDATE (LWW win) for Category {entity_id}", details=payload)
                        notification_data = CategoryPayload.model_validate(updated_category)
                    else:
                        infoLog(MODULE_NAME, f"Skipped CREATE as UPDATE (LWW loss/equal) for Category {entity_id}", details=payload)
                        notification_data = CategoryPayload.model_validate(existing_category)
                        authoritative_data_used = True
                else:
                    if isinstance(payload, CategoryPayload):
                        new_category = crud_category.create_category(db=db, category_in=payload)
                        infoLog(MODULE_NAME, f"Created Category {entity_id}", details=payload)
                        notification_data = CategoryPayload.model_validate(new_category)
                    else:
                        error_msg = "Payload mismatch for Category CREATE"
                        errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                        return False, error_msg

            elif operation_type == SyncOperationType.UPDATE:
                if not isinstance(payload, CategoryPayload):
                    error_msg = "Invalid payload type for Category UPDATE"
                    errorLog(MODULE_NAME, error_msg, details={"payload": payload, "entry_id": entry.id})
                    return False, error_msg
                db_category = crud_category.get_category(db=db, category_id=entity_id)
                if db_category:
                    if incoming_updated_at and db_category.updatedAt and incoming_updated_at > db_category.updatedAt:
                        updated_category = crud_category.update_category(db=db, db_category=db_category, category_in=payload)
                        infoLog(MODULE_NAME, f"Updated Category {entity_id} (LWW win)", details=payload)
                        notification_data = CategoryPayload.model_validate(updated_category)
                    else:
                        infoLog(MODULE_NAME, f"Skipped Category UPDATE {entity_id} (LWW loss/equal or no timestamp)", details=payload)
                        notification_data = CategoryPayload.model_validate(db_category)
                        authoritative_data_used = True
                else:
                    new_category = crud_category.create_category(db=db, category_in=payload)
                    infoLog(MODULE_NAME, f"Created Category {entity_id} during UPDATE (upsert)", details=payload)
                    notification_data = CategoryPayload.model_validate(new_category)

            elif operation_type == SyncOperationType.DELETE:
                deleted_category = crud_category.delete_category(db=db, category_id=entity_id)
                if deleted_category:
                    infoLog(MODULE_NAME, f"Deleted Category {entity_id}")
                    notification_data = DeletePayload(id=entity_id)
                else:
                    infoLog(MODULE_NAME, f"Category {entity_id} not found for DELETE")
                    notification_data = DeletePayload(id=entity_id)
                    authoritative_data_used = True

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
        categories_db = crud_category.get_categories(db=db)
        category_groups_db = crud_category_group.get_category_groups(db=db)

        accounts_payload = [AccountPayload.model_validate(acc) for acc in accounts_db]
        account_groups_payload = [AccountGroupPayload.model_validate(ag) for ag in account_groups_db]
        categories_payload = [CategoryPayload.model_validate(cat) for cat in categories_db]
        category_groups_payload = [CategoryGroupPayload.model_validate(cg) for cg in category_groups_db]

        initial_data = InitialDataPayload(
            accounts=accounts_payload,
            account_groups=account_groups_payload,
            categories=categories_payload,
            category_groups=category_groups_payload
        )
        infoLog(MODULE_NAME, f"Successfully retrieved initial data for tenant {tenant_id}. Accounts: {len(accounts_payload)}, AccountGroups: {len(account_groups_payload)}, Categories: {len(categories_payload)}, CategoryGroups: {len(category_groups_payload)}")
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
                        'image': account.image,
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
                        'image': group.image,
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
