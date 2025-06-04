import asyncio # Required for running async websocket calls from sync functions if needed, or making functions async
from sqlalchemy.orm import Session
from typing import List, Optional
# from uuid import UUID # IDs are strings now

from app.models.financial_models import AccountGroup
from app.websocket.schemas import (
    AccountGroupPayload,
    DataUpdateNotificationMessage,
    EntityType,
    SyncOperationType,
    DeletePayload,
    ServerEventType
)
from app.websocket.connection_manager import ConnectionManager, manager as websocket_manager_instance # Use the global manager instance


def get_account_group(db: Session, account_group_id: str) -> Optional[AccountGroup]:
    """
    Retrieves an AccountGroup by its ID.
    IDs are stored as strings (UUIDs represented as strings).
    """
    return db.query(AccountGroup).filter(AccountGroup.id == account_group_id).first()

def get_account_groups(db: Session, skip: int = 0, limit: int = 100) -> List[AccountGroup]:
    """
    Retrieves a list of AccountGroups.
    """
    return db.query(AccountGroup).offset(skip).limit(limit).all()

async def create_account_group(
    db: Session,
    *,
    account_group_in: AccountGroupPayload,
    tenant_id: str,
    websocket_manager: ConnectionManager = websocket_manager_instance
) -> AccountGroup:
    """
    Creates a new AccountGroup and notifies connected clients via WebSocket.
    The 'id' from account_group_in.id (which is a string UUID from frontend) will be used.
    """
    db_account_group = AccountGroup(
        id=account_group_in.id, # Use the ID from payload
        name=account_group_in.name,
        sortOrder=account_group_in.sortOrder,
        image=account_group_in.image
        # createdAt and updatedAt have defaults
    )
    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)

    # Notify via WebSocket
    message = DataUpdateNotificationMessage(
        event_type=ServerEventType.DATA_UPDATE,
        tenant_id=tenant_id,
        entity_type=EntityType.ACCOUNT_GROUP,
        operation_type=SyncOperationType.CREATE,
        data=AccountGroupPayload.model_validate(db_account_group) # Convert SQLAlchemy model to Pydantic model
    )
    await websocket_manager.broadcast_json_to_tenant(message.model_dump(), tenant_id)

    return db_account_group

async def update_account_group(
    db: Session,
    *,
    db_account_group: AccountGroup,
    account_group_in: AccountGroupPayload,
    tenant_id: str,
    websocket_manager: ConnectionManager = websocket_manager_instance
) -> AccountGroup:
    """
    Updates an existing AccountGroup and notifies connected clients via WebSocket.
    account_group_in contains all fields for update, not partial.
    """
    db_account_group.name = account_group_in.name
    db_account_group.sortOrder = account_group_in.sortOrder
    db_account_group.image = account_group_in.image
    # updatedAt will be updated by the model's onupdate

    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)

    # Notify via WebSocket
    message = DataUpdateNotificationMessage(
        event_type=ServerEventType.DATA_UPDATE,
        tenant_id=tenant_id,
        entity_type=EntityType.ACCOUNT_GROUP,
        operation_type=SyncOperationType.UPDATE,
        data=AccountGroupPayload.model_validate(db_account_group) # Convert SQLAlchemy model to Pydantic model
    )
    await websocket_manager.broadcast_json_to_tenant(message.model_dump(), tenant_id)

    return db_account_group

async def delete_account_group(
    db: Session,
    *,
    account_group_id: str,
    tenant_id: str,
    websocket_manager: ConnectionManager = websocket_manager_instance
) -> Optional[AccountGroup]:
    """
    Deletes an AccountGroup by its ID and notifies connected clients via WebSocket.
    Returns the deleted object or None if not found.
    """
    db_account_group = get_account_group(db, account_group_id=account_group_id)
    if db_account_group:
        deleted_account_group_id = db_account_group.id
        db.delete(db_account_group)
        db.commit()

        # Notify via WebSocket
        message = DataUpdateNotificationMessage(
            event_type=ServerEventType.DATA_UPDATE,
            tenant_id=tenant_id,
            entity_type=EntityType.ACCOUNT_GROUP,
            operation_type=SyncOperationType.DELETE,
            data=DeletePayload(id=deleted_account_group_id)
        )
        await websocket_manager.broadcast_json_to_tenant(message.model_dump(), tenant_id)
        return db_account_group # Return the object that was deleted (now detached from session)
    return None

# Potentially a function to get AccountGroups modified since a certain timestamp,
# similar to what's in crud_account.py, could be added here if needed for sync later.
# from datetime import datetime # Would be needed if uncommenting
# def get_account_groups_modified_since(db: Session, *, timestamp: datetime) -> List[AccountGroup]:
#     return db.query(AccountGroup).filter(AccountGroup.updatedAt >= timestamp).all()
