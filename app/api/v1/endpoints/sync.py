from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session  # Geändert von sqlmodel zu sqlalchemy für Kompatibilität mit TenantSessionLocal

from app import crud
from app.api.deps import get_tenant_db_session, get_current_tenant_id  # Direkter Import der neuen Dependencies
from app.models.account import Account, AccountCreate, AccountRead, AccountUpdate
from app.models.account_group import (
    AccountGroup,
    AccountGroupCreate,
    AccountGroupRead,
    AccountGroupUpdate,
)
from app.models.sync import (
    SyncEntityType,
    SyncOperationType,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponseItem,
    SyncPushResponse,
    SyncQueueItemIn,
)
# Importiere das Tenant-Modell, falls benötigt für die Authentifizierung/Autorisierung
# from app.models.user_tenant_models import Tenant

router = APIRouter()


@router.post("/push", response_model=SyncPushResponse)
async def push_changes(  # Changed to async
    *,
    db: Session = Depends(get_tenant_db_session),
    sync_request: SyncPushRequest,
    current_tenant_id: str = Depends(get_current_tenant_id),
) -> SyncPushResponse:
    """Handles a list of changes from the frontend."""
    response_items: List[SyncPushResponseItem] = []

    for item in sync_request.changes:
        response_item = SyncPushResponseItem(
            frontend_sync_queue_item_id=item.id,
            entity_id=item.entity_id,
            entity_type=item.entity_type,
            success=False,
        )
        try:
            if item.entity_type == SyncEntityType.ACCOUNT:
                response_item.updated_entity = await handle_account_sync(  # Added await
                    db=db, item=item, tenant_id=current_tenant_id
                )
            elif item.entity_type == SyncEntityType.ACCOUNT_GROUP:
                response_item.updated_entity = await handle_account_group_sync(  # Added await
                    db=db, item=item, tenant_id=current_tenant_id
                )
            else:
                response_item.message = f"Entity type {item.entity_type} not supported."
                response_item.error_code = "UNSUPPORTED_ENTITY_TYPE"
                response_items.append(response_item)
                continue

            response_item.success = True
            if item.operation == SyncOperationType.DELETE:
                response_item.message = f"{item.entity_type} {item.entity_id} successfully deleted."
            else:
                response_item.message = f"{item.entity_type} {item.entity_id} successfully processed."

        except HTTPException as e:
            response_item.success = False
            response_item.message = str(e.detail)
            response_item.error_code = "HTTP_EXCEPTION"  # oder spezifischer
        except ValueError as e:  # Fängt Validierungsfehler von Pydantic/SQLModel ab
            response_item.success = False
            response_item.message = str(e)
            response_item.error_code = "VALIDATION_ERROR"
        except Exception as e:
            # Logge den Fehler serverseitig
            # logger.error(f"Error processing sync item {item.id}: {e}", exc_info=True)
            response_item.success = False
            response_item.message = "An unexpected error occurred."
            response_item.error_code = "INTERNAL_SERVER_ERROR"

        response_items.append(response_item)

    return SyncPushResponse(results=response_items)


async def handle_account_sync(  # Changed to async
    db: Session, item: SyncQueueItemIn, tenant_id: str
) -> Optional[AccountRead]:
    entity_id = item.entity_id
    payload = item.payload  # This is a dict

    payload_updated_at_str = payload.get("updated_at")
    if not payload_updated_at_str:
        raise HTTPException(
            status_code=400,
            detail=f"Missing 'updated_at' in payload for Account {entity_id}."
        )
    try:
        payload_updated_at = datetime.fromisoformat(payload_updated_at_str.replace("Z", "+00:00"))
        if payload_updated_at.tzinfo is None:
            payload_updated_at = payload_updated_at.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid 'updated_at' format for Account {entity_id}. Expected ISO format."
        )

    if item.operation == SyncOperationType.CREATE:
        existing_account = crud.account.get_account(db=db, account_id=entity_id)
        if existing_account:
            if payload_updated_at >= existing_account.updated_at.replace(tzinfo=timezone.utc):
                account_in_update = crud.AccountPayload(**payload)
                updated_account = await crud.account.update_account(  # Added await
                    db=db, db_account=existing_account, account_in=account_in_update, tenant_id=tenant_id
                )
                return AccountRead.model_validate(updated_account)
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"Conflict: Account {entity_id} already exists with a newer version in the backend."
                )

        account_in_create = AccountCreate(**payload, id=entity_id)
        new_account_data = account_in_create.model_dump()
        new_account_data["created_at"] = payload.get("created_at", datetime.utcnow())
        new_account_data["updated_at"] = payload_updated_at

        valid_fields = Account.model_fields.keys()
        filtered_data = {k: v for k, v in new_account_data.items() if k in valid_fields}

        created_account = await crud.account.create_account(  # Added await
            db=db, account_in=crud.AccountPayload(**filtered_data), tenant_id=tenant_id
        )
        return AccountRead.model_validate(created_account)

    db_account = crud.account.get_account(db=db, account_id=entity_id)
    if not db_account:
        if item.operation == SyncOperationType.UPDATE:
            raise HTTPException(
                status_code=404, detail=f"Account {entity_id} not found for update."
            )
        elif item.operation == SyncOperationType.DELETE:
            return None

    if item.operation == SyncOperationType.UPDATE:
        if not db_account:  # Sollte durch obige Prüfung abgedeckt sein
            raise HTTPException(status_code=404, detail=f"Account {entity_id} not found.")
        db_updated_at = db_account.updated_at.replace(tzinfo=timezone.utc) if db_account.updated_at.tzinfo is None else db_account.updated_at

        if payload_updated_at >= db_updated_at:
            account_in_update = crud.AccountPayload(**payload)
            updated_account = await crud.account.update_account(  # Added await
                db=db, db_account=db_account, account_in=account_in_update, tenant_id=tenant_id
            )
            return AccountRead.model_validate(updated_account)
        else:
            raise HTTPException(
                status_code=409,  # Conflict
                detail=f"Conflict: Account {entity_id} in backend is newer. Frontend change rejected."
            )

    if item.operation == SyncOperationType.DELETE:
        if not db_account:
            return None
        await crud.account.delete_account(db=db, account_id=db_account.id, tenant_id=tenant_id)  # Added await
        return None
    return None


async def handle_account_group_sync(  # Changed to async
    db: Session, item: SyncQueueItemIn, tenant_id: str
) -> Optional[AccountGroupRead]:
    entity_id = item.entity_id
    payload = item.payload  # This is a dict

    payload_updated_at_str = payload.get("updated_at")
    if not payload_updated_at_str:
        raise HTTPException(
            status_code=400,
            detail=f"Missing 'updated_at' in payload for AccountGroup {entity_id}."
        )
    try:
        payload_updated_at = datetime.fromisoformat(payload_updated_at_str.replace("Z", "+00:00"))
        if payload_updated_at.tzinfo is None:
            payload_updated_at = payload_updated_at.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid 'updated_at' format for AccountGroup {entity_id}. Expected ISO format."
        )

    if item.operation == SyncOperationType.CREATE:
        existing_group = crud.account_group.get_account_group(db=db, account_group_id=entity_id)
        if existing_group:
            if payload_updated_at >= existing_group.updated_at.replace(tzinfo=timezone.utc):
                group_in_update = crud.AccountGroupPayload(**payload)
                updated_group = await crud.account_group.update_account_group(  # Added await
                    db=db, db_account_group=existing_group, account_group_in=group_in_update, tenant_id=tenant_id
                )
                return AccountGroupRead.model_validate(updated_group)
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"Conflict: AccountGroup {entity_id} already exists with a newer version."
                )

        group_in_create = AccountGroupCreate(**payload, id=entity_id)
        new_group_data = group_in_create.model_dump()
        new_group_data["created_at"] = payload.get("created_at", datetime.utcnow())
        new_group_data["updated_at"] = payload_updated_at

        valid_fields = AccountGroup.model_fields.keys()
        filtered_data = {k: v for k, v in new_group_data.items() if k in valid_fields}

        created_group = await crud.account_group.create_account_group(  # Added await
            db=db, account_group_in=crud.AccountGroupPayload(**filtered_data), tenant_id=tenant_id
        )
        return AccountGroupRead.model_validate(created_group)

    db_account_group = crud.account_group.get_account_group(db=db, account_group_id=entity_id)
    if not db_account_group:
        if item.operation == SyncOperationType.UPDATE:
            raise HTTPException(
                status_code=404, detail=f"AccountGroup {entity_id} not found for update."
            )
        elif item.operation == SyncOperationType.DELETE:
            return None

    if item.operation == SyncOperationType.UPDATE:
        if not db_account_group:
            raise HTTPException(status_code=404, detail=f"AccountGroup {entity_id} not found.")

        db_updated_at = db_account_group.updated_at.replace(tzinfo=timezone.utc) if db_account_group.updated_at.tzinfo is None else db_account_group.updated_at
        if payload_updated_at >= db_updated_at:
            group_in_update = crud.AccountGroupPayload(**payload)
            updated_group = await crud.account_group.update_account_group(  # Added await
                db=db, db_account_group=db_account_group, account_group_in=group_in_update, tenant_id=tenant_id
            )
            return AccountGroupRead.model_validate(updated_group)
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Conflict: AccountGroup {entity_id} in backend is newer. Frontend change rejected."
            )

    if item.operation == SyncOperationType.DELETE:
        if not db_account_group:
            return None
        await crud.account_group.delete_account_group(db=db, account_group_id=db_account_group.id, tenant_id=tenant_id)  # Added await, delete_account_group expects id
        return None
    return None


@router.get("/pull/{entity_type}", response_model=SyncPullResponse)
async def pull_changes(  # Changed to async
    *,
    db: Session = Depends(get_tenant_db_session),
    entity_type: SyncEntityType,
    last_sync_timestamp_str: Optional[str] = Query(None, alias="lastSyncTimestamp", description="ISO 8601 Format"),
    current_tenant_id: str = Depends(get_current_tenant_id),  # current_tenant_id is available but not directly used by the get_... CRUD functions below
) -> SyncPullResponse:
    """Returns changes for a specific entity type since an optional timestamp."""
    new_or_updated_entities: List[Any] = []

    deleted_ids_placeholder: List[UUID] = []  # Platzhalter, da Hard-Delete

    last_sync_timestamp: Optional[datetime] = None
    if last_sync_timestamp_str:
        try:
            last_sync_timestamp = datetime.fromisoformat(last_sync_timestamp_str.replace("Z", "+00:00"))
            if last_sync_timestamp.tzinfo is None:  # Sicherstellen, dass es timezone-aware ist
                last_sync_timestamp = last_sync_timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid last_sync_timestamp format. Expected ISO 8601.")

    if entity_type == SyncEntityType.ACCOUNT:
        if last_sync_timestamp:
            accounts = crud.account.get_accounts_modified_since(
                db=db, timestamp=last_sync_timestamp  # tenant_id not needed for this specific crud function as per its definition
            )
        else:
            accounts = crud.account.get_accounts(db=db, limit=10000)
        new_or_updated_entities.extend([AccountRead.model_validate(acc) for acc in accounts])

    elif entity_type == SyncEntityType.ACCOUNT_GROUP:
        if last_sync_timestamp:
            # crud.account_group.get_account_groups_modified_since is not async (and currently commented out)
            # Assuming it would be:
            # account_groups = crud.account_group.get_account_groups_modified_since(
            #     db=db, timestamp=last_sync_timestamp
            # )
            # For now, let's assume it's not implemented or fall back to get_account_groups
            # This part needs clarification if get_account_groups_modified_since is to be used.
            # Fallback to getting all if modified_since is not available/implemented for account_group
            account_groups = crud.account_group.get_account_groups(db=db, limit=10000)  # tenant_id not needed
        else:
            account_groups = crud.account_group.get_account_groups(db=db, limit=10000)  # tenant_id not needed
        new_or_updated_entities.extend([AccountGroupRead.model_validate(ag) for ag in account_groups])
    else:
        raise HTTPException(status_code=400, detail=f"Entity type {entity_type} not supported for pull.")

    current_utc_time = datetime.now(timezone.utc)

    return SyncPullResponse(
        new_or_updated=new_or_updated_entities,
        deleted_ids=deleted_ids_placeholder,  # Hier müssten bei Soft-Delete die IDs rein
        new_last_synced_timestamp=current_utc_time,
    )
