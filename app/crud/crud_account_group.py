import asyncio  # Required for running async websocket calls from sync functions if needed, or making functions async
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import WebSocket  # Added for type hinting
# from uuid import UUID # IDs are strings now

from app.models.financial_models import AccountGroup
from app.models import schemas # Added import
from app.websocket.schemas import (
    # AccountGroupPayload, # Replaced by schemas.AccountGroupUpdate
    DataUpdateNotificationMessage,
    EntityType,
    SyncOperationType,
    DeletePayload,
    ServerEventType
)
from app.websocket.connection_manager import ConnectionManager, manager as websocket_manager_instance  # Use the global manager instance
from datetime import datetime


def get_account_group(db: Session, account_group_id: str) -> Optional[AccountGroup]:
    return db.query(AccountGroup).filter(AccountGroup.id == account_group_id).first()


def get_account_groups(db: Session, skip: int = 0, limit: int = 100) -> List[AccountGroup]:
    return db.query(AccountGroup).offset(skip).limit(limit).all()


def create_account_group(  # Changed to sync
    db: Session,
    *,
    account_group_in: schemas.AccountGroupPayload, # Kept AccountGroupPayload for create
    # tenant_id: str, # Removed
    # websocket_manager: ConnectionManager = websocket_manager_instance, # Removed
    # exclude_websocket: Optional[WebSocket] = None # Removed
) -> AccountGroup:
    """Creates a new AccountGroup."""
    db_account_group = AccountGroup(
        id=account_group_in.id,  # Use the ID from payload
        name=account_group_in.name,
        sortOrder=account_group_in.sortOrder,
        logo_path=account_group_in.logo_path,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=account_group_in.updated_at if account_group_in.updated_at else datetime.utcnow()
    )
    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)

    # WebSocket notification logic is moved to the service layer.

    return db_account_group


def update_account_group(  # Changed to sync
    db: Session,
    *,
    db_account_group: AccountGroup,
    account_group_in: schemas.AccountGroupUpdate, # Changed to AccountGroupUpdate
    # tenant_id: str, # Removed
    # websocket_manager: ConnectionManager = websocket_manager_instance, # Removed
    # exclude_websocket: Optional[WebSocket] = None # Removed
) -> AccountGroup:
    """Updates an existing AccountGroup."""
    db_account_group.name = account_group_in.name
    db_account_group.sortOrder = account_group_in.sortOrder
    if hasattr(account_group_in, 'logo_path'): # Check if logo_path is in the payload
        db_account_group.logo_path = account_group_in.logo_path

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    if account_group_in.updated_at:
        db_account_group.updatedAt = account_group_in.updated_at

    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)

    # WebSocket notification logic is moved to the service layer.

    return db_account_group


def delete_account_group(  # Changed to sync
    db: Session,
    *,
    account_group_id: str,
    # tenant_id: str, # Removed
    # websocket_manager: ConnectionManager = websocket_manager_instance, # Removed
    # exclude_websocket: Optional[WebSocket] = None # Removed
) -> Optional[AccountGroup]:
    """Deletes an AccountGroup by its ID."""
    db_account_group = get_account_group(db, account_group_id=account_group_id)
    if db_account_group:
        deleted_account_group_id = db_account_group.id
        db.delete(db_account_group)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return db_account_group  # Return the object that was deleted (now detached from session)
    return None

def get_account_groups_modified_since(
    db: Session, *, timestamp: datetime
) -> List[AccountGroup]:
    """Retrieves all account groups that were created or updated since the given timestamp."""
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(AccountGroup).filter(AccountGroup.updatedAt >= timestamp).all()
