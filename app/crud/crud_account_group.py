import asyncio # Required for running async websocket calls from sync functions if needed, or making functions async
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import WebSocket # Added for type hinting
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

def create_account_group( # Changed to sync
    db: Session,
    *,
    account_group_in: AccountGroupPayload,
    # tenant_id: str, # Removed
    # websocket_manager: ConnectionManager = websocket_manager_instance, # Removed
    # exclude_websocket: Optional[WebSocket] = None # Removed
) -> AccountGroup:
    """
    Creates a new AccountGroup.
    The 'id' from account_group_in.id (which is a string UUID from frontend) will be used.
    updatedAt from payload is respected.
    """
    db_account_group = AccountGroup(
        id=account_group_in.id, # Use the ID from payload
        name=account_group_in.name,
        sortOrder=account_group_in.sortOrder,
        image=account_group_in.image,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=account_group_in.updated_at if account_group_in.updated_at else datetime.utcnow()
    )
    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)

    # WebSocket notification logic is moved to the service layer.

    return db_account_group

def update_account_group( # Changed to sync
    db: Session,
    *,
    db_account_group: AccountGroup,
    account_group_in: AccountGroupPayload,
    # tenant_id: str, # Removed
    # websocket_manager: ConnectionManager = websocket_manager_instance, # Removed
    # exclude_websocket: Optional[WebSocket] = None # Removed
) -> AccountGroup:
    """
    Updates an existing AccountGroup.
    account_group_in contains all fields for update, not partial.
    updatedAt from payload is respected if provided.
    """
    db_account_group.name = account_group_in.name
    db_account_group.sortOrder = account_group_in.sortOrder
    db_account_group.image = account_group_in.image

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    if account_group_in.updated_at:
        db_account_group.updatedAt = account_group_in.updated_at

    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)

    # WebSocket notification logic is moved to the service layer.

    return db_account_group

def delete_account_group( # Changed to sync
    db: Session,
    *,
    account_group_id: str,
    # tenant_id: str, # Removed
    # websocket_manager: ConnectionManager = websocket_manager_instance, # Removed
    # exclude_websocket: Optional[WebSocket] = None # Removed
) -> Optional[AccountGroup]:
    """
    Deletes an AccountGroup by its ID.
    Returns the deleted object or None if not found.
    """
    db_account_group = get_account_group(db, account_group_id=account_group_id)
    if db_account_group:
        deleted_account_group_id = db_account_group.id
        db.delete(db_account_group)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return db_account_group # Return the object that was deleted (now detached from session)
    return None

# Potentially a function to get AccountGroups modified since a certain timestamp,
# similar to what's in crud_account.py, could be added here if needed for sync later.
# from datetime import datetime # Would be needed if uncommenting
# def get_account_groups_modified_since(db: Session, *, timestamp: datetime) -> List[AccountGroup]:
#     return db.query(AccountGroup).filter(AccountGroup.updatedAt >= timestamp).all()
