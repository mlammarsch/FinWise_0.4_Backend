from sqlalchemy.orm import Session
from app.websocket.schemas import SyncQueueEntry, EntityType, SyncOperationType, AccountPayload, AccountGroupPayload, DeletePayload
from app.db.tenant_db import create_tenant_db_engine, TenantSessionLocal
from app.models.financial_models import TenantBase # Important: Use the Base from financial_models
from app.crud import crud_account, crud_account_group
from app.utils.logger import infoLog, errorLog, debugLog

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

def process_sync_entry(entry: SyncQueueEntry) -> bool:
    """
    Processes a single SyncQueueEntry and performs the necessary CRUD operation
    in the respective tenant's database.
    """
    debugLog(MODULE_NAME, f"Processing sync entry: {entry.id} for tenant {entry.tenantId}", details=entry.model_dump())

    db: Optional[Session] = None
    try:
        db = get_tenant_db_session(entry.tenantId)
        if db is None:
            errorLog(MODULE_NAME, f"Could not get DB session for tenant {entry.tenantId}", details={"entry_id": entry.id})
            return False

        entity_type = entry.entityType
        operation_type = entry.operationType
        payload = entry.payload
        entity_id = entry.entityId

        if entity_type == EntityType.ACCOUNT:
            if operation_type == SyncOperationType.CREATE:
                if not isinstance(payload, AccountPayload):
                    errorLog(MODULE_NAME, "Invalid payload type for Account CREATE", details=payload)
                    return False
                crud_account.create_account(db=db, account_in=payload)
                infoLog(MODULE_NAME, f"Created Account {payload.id} for tenant {entry.tenantId}")
            elif operation_type == SyncOperationType.UPDATE:
                if not isinstance(payload, AccountPayload):
                    errorLog(MODULE_NAME, "Invalid payload type for Account UPDATE", details=payload)
                    return False
                db_account = crud_account.get_account(db=db, account_id=entity_id)
                if db_account:
                    crud_account.update_account(db=db, db_account=db_account, account_in=payload)
                    infoLog(MODULE_NAME, f"Updated Account {entity_id} for tenant {entry.tenantId}")
                else:
                    # If account not found for update, we could choose to create it (upsert)
                    # For now, log an error. This might happen if a create message was missed.
                    errorLog(MODULE_NAME, f"Account {entity_id} not found for UPDATE in tenant {entry.tenantId}")
                    # Potentially create it:
                    # crud_account.create_account(db=db, account_in=payload)
                    # infoLog(MODULE_NAME, f"Created Account {payload.id} (during update attempt) for tenant {entry.tenantId}")
                    return False
            elif operation_type == SyncOperationType.DELETE:
                deleted_account = crud_account.delete_account(db=db, account_id=entity_id)
                if deleted_account:
                    infoLog(MODULE_NAME, f"Deleted Account {entity_id} for tenant {entry.tenantId}")
                else:
                    infoLog(MODULE_NAME, f"Account {entity_id} not found for DELETE in tenant {entry.tenantId} (already deleted or never existed)")

        elif entity_type == EntityType.ACCOUNT_GROUP:
            if operation_type == SyncOperationType.CREATE:
                if not isinstance(payload, AccountGroupPayload):
                    errorLog(MODULE_NAME, "Invalid payload type for AccountGroup CREATE", details=payload)
                    return False
                crud_account_group.create_account_group(db=db, account_group_in=payload)
                infoLog(MODULE_NAME, f"Created AccountGroup {payload.id} for tenant {entry.tenantId}")
            elif operation_type == SyncOperationType.UPDATE:
                if not isinstance(payload, AccountGroupPayload):
                    errorLog(MODULE_NAME, "Invalid payload type for AccountGroup UPDATE", details=payload)
                    return False
                db_account_group = crud_account_group.get_account_group(db=db, account_group_id=entity_id)
                if db_account_group:
                    crud_account_group.update_account_group(db=db, db_account_group=db_account_group, account_group_in=payload)
                    infoLog(MODULE_NAME, f"Updated AccountGroup {entity_id} for tenant {entry.tenantId}")
                else:
                    errorLog(MODULE_NAME, f"AccountGroup {entity_id} not found for UPDATE in tenant {entry.tenantId}")
                    # Potentially create it:
                    # crud_account_group.create_account_group(db=db, account_group_in=payload)
                    # infoLog(MODULE_NAME, f"Created AccountGroup {payload.id} (during update attempt) for tenant {entry.tenantId}")
                    return False
            elif operation_type == SyncOperationType.DELETE:
                # Ensure payload for delete is just an ID or None
                if payload is not None and not isinstance(payload, DeletePayload):
                     errorLog(MODULE_NAME, "Invalid payload type for AccountGroup DELETE, should be DeletePayload or None", details=payload)
                     # return False # Or proceed if entityId is reliable

                deleted_group = crud_account_group.delete_account_group(db=db, account_group_id=entity_id)
                if deleted_group:
                    infoLog(MODULE_NAME, f"Deleted AccountGroup {entity_id} for tenant {entry.tenantId}")
                else:
                    infoLog(MODULE_NAME, f"AccountGroup {entity_id} not found for DELETE in tenant {entry.tenantId} (already deleted or never existed)")

        else:
            errorLog(MODULE_NAME, f"Unknown entity type: {entity_type}", details={"entry_id": entry.id})
            return False

        return True

    except Exception as e:
        errorLog(MODULE_NAME, f"Error processing sync entry {entry.id} for tenant {entry.tenantId}: {str(e)}",
                   details={"entry": entry.model_dump(), "error": str(e)})
        return False
    finally:
        if db:
            db.close()
