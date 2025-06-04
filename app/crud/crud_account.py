import asyncio # Required for running async websocket calls from sync functions if needed, or making functions async
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import WebSocket # Added for type hinting

from app.models.financial_models import Account
from app.websocket.schemas import (
    AccountPayload,
    DataUpdateNotificationMessage,
    EntityType,
    SyncOperationType,
    DeletePayload,
    ServerEventType
)
from app.websocket.connection_manager import ConnectionManager, manager as websocket_manager_instance # Use the global manager instance


async def create_account(
    db: Session,
    *,
    account_in: AccountPayload,
    tenant_id: str,
    websocket_manager: ConnectionManager = websocket_manager_instance,
    exclude_websocket: Optional[WebSocket] = None
) -> Account:
    """
    Creates a new Account and notifies connected clients via WebSocket.
    Allows excluding a specific websocket from notification.
    The 'id' from account_in.id (which is a string UUID from frontend) will be used.
    """
    db_account = Account(
        id=account_in.id,
        name=account_in.name,
        description=account_in.description,
        note=account_in.note,
        accountType=account_in.accountType.value, # Use enum value
        isActive=account_in.isActive,
        isOfflineBudget=account_in.isOfflineBudget,
        accountGroupId=account_in.accountGroupId,
        sortOrder=account_in.sortOrder,
        iban=account_in.iban,
        balance=account_in.balance,
        creditLimit=account_in.creditLimit,
        offset=account_in.offset,
        image=account_in.image
        # createdAt and updatedAt have defaults
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)

    # Notify via WebSocket
    message = DataUpdateNotificationMessage(
        event_type=ServerEventType.DATA_UPDATE,
        tenant_id=tenant_id,
        entity_type=EntityType.ACCOUNT,
        operation_type=SyncOperationType.CREATE,
        data=AccountPayload.model_validate(db_account) # Convert SQLAlchemy model to Pydantic model
    )
    await websocket_manager.broadcast_json_to_tenant(message.model_dump(), tenant_id, exclude_websocket=exclude_websocket)

    return db_account


def get_account(db: Session, *, account_id: str) -> Optional[Account]:
    """
    Retrieves an Account by its ID.
    IDs are stored as strings.
    """
    return db.query(Account).filter(Account.id == account_id).first()


def get_accounts(
    db: Session, skip: int = 0, limit: int = 100
) -> List[Account]:
    """
    Retrieves a list of Accounts.
    """
    return db.query(Account).offset(skip).limit(limit).all()


async def update_account(
    db: Session,
    *,
    db_account: Account,
    account_in: AccountPayload,
    tenant_id: str,
    websocket_manager: ConnectionManager = websocket_manager_instance,
    exclude_websocket: Optional[WebSocket] = None
) -> Account:
    """
    Updates an existing Account and notifies connected clients via WebSocket.
    Allows excluding a specific websocket from notification.
    account_in contains all fields for update.
    """
    db_account.name = account_in.name
    db_account.description = account_in.description
    db_account.note = account_in.note
    db_account.accountType = account_in.accountType.value # Use enum value
    db_account.isActive = account_in.isActive
    db_account.isOfflineBudget = account_in.isOfflineBudget
    db_account.accountGroupId = account_in.accountGroupId
    db_account.sortOrder = account_in.sortOrder
    db_account.iban = account_in.iban
    db_account.balance = account_in.balance
    db_account.creditLimit = account_in.creditLimit
    db_account.offset = account_in.offset
    db_account.image = account_in.image
    # updatedAt will be updated by the model's onupdate

    db.add(db_account)
    db.commit()
    db.refresh(db_account)

    # Notify via WebSocket
    message = DataUpdateNotificationMessage(
        event_type=ServerEventType.DATA_UPDATE,
        tenant_id=tenant_id,
        entity_type=EntityType.ACCOUNT,
        operation_type=SyncOperationType.UPDATE,
        data=AccountPayload.model_validate(db_account) # Convert SQLAlchemy model to Pydantic model
    )
    await websocket_manager.broadcast_json_to_tenant(message.model_dump(), tenant_id, exclude_websocket=exclude_websocket)

    return db_account


async def delete_account(
    db: Session,
    *,
    account_id: str,
    tenant_id: str,
    websocket_manager: ConnectionManager = websocket_manager_instance,
    exclude_websocket: Optional[WebSocket] = None
) -> Optional[Account]:
    """
    Deletes an Account by its ID and notifies connected clients via WebSocket.
    Allows excluding a specific websocket from notification.
    Returns the deleted object or None if not found.
    """
    db_account = get_account(db, account_id=account_id)
    if db_account:
        # Store id before deleting, as it might not be accessible after deletion from session
        deleted_account_id = db_account.id
        db.delete(db_account)
        db.commit()

        # Notify via WebSocket
        message = DataUpdateNotificationMessage(
            event_type=ServerEventType.DATA_UPDATE,
            tenant_id=tenant_id,
            entity_type=EntityType.ACCOUNT,
            operation_type=SyncOperationType.DELETE,
            data=DeletePayload(id=deleted_account_id)
        )
        await websocket_manager.broadcast_json_to_tenant(message.model_dump(), tenant_id, exclude_websocket=exclude_websocket)
        return db_account # Return the object that was deleted (now detached from session)
    return None


def get_accounts_modified_since(
    db: Session, *, timestamp: datetime
) -> List[Account]:
    """
    Retrieves all accounts that were created or updated since the given timestamp.
    """
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(Account).filter(Account.updatedAt >= timestamp).all()
