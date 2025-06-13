import asyncio  # Required for running async websocket calls from sync functions if needed, or making functions async
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import WebSocket  # Added for type hinting

from app.models.financial_models import Account
from app.websocket.schemas import (
    AccountPayload,
    DataUpdateNotificationMessage,
    EntityType,
    SyncOperationType,
    DeletePayload,
    ServerEventType,
)
from app.websocket.connection_manager import (
    ConnectionManager,
    manager as websocket_manager_instance,
)  # Use the global manager instance


def create_account(  # Changed to sync, WebSocket logic moved to service layer
    db: Session,
    *,
    account_in: AccountPayload,
) -> Account:
    """Creates a new Account."""
    # Robuste Behandlung von accountType (kann String oder Enum sein)
    account_type_value = account_in.accountType.value if hasattr(account_in.accountType, 'value') else account_in.accountType

    db_account = Account(
        id=account_in.id,
        name=account_in.name,
        description=account_in.description,
        note=account_in.note,
        accountType=account_type_value,
        isActive=account_in.isActive,
        isOfflineBudget=account_in.isOfflineBudget,
        accountGroupId=account_in.accountGroupId,
        sortOrder=account_in.sortOrder,
        iban=account_in.iban,
        balance=account_in.balance,
        creditLimit=account_in.creditLimit,
        offset=account_in.offset,
        image=account_in.image,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=account_in.updated_at if account_in.updated_at else datetime.utcnow(),
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)

    # WebSocket notification logic is moved to the service layer
    # to handle LWW decisions before notifying.

    return db_account


def get_account(db: Session, *, account_id: str) -> Optional[Account]:
    """Retrieves an Account by its ID."""
    return db.query(Account).filter(Account.id == account_id).first()


def get_accounts(db: Session, skip: int = 0, limit: int = 100) -> List[Account]:
    """Retrieves a list of Accounts."""
    return db.query(Account).offset(skip).limit(limit).all()


def update_account(  # Changed to sync
    db: Session,
    *,
    db_account: Account,
    account_in: AccountPayload,
) -> Account:
    """Updates an existing Account."""
    # Robuste Behandlung von accountType (kann String oder Enum sein)
    account_type_value = account_in.accountType.value if hasattr(account_in.accountType, 'value') else account_in.accountType

    db_account.name = account_in.name
    db_account.description = account_in.description
    db_account.note = account_in.note
    db_account.accountType = account_type_value
    db_account.isActive = account_in.isActive
    db_account.isOfflineBudget = account_in.isOfflineBudget
    db_account.accountGroupId = account_in.accountGroupId
    db_account.sortOrder = account_in.sortOrder
    db_account.iban = account_in.iban
    db_account.balance = account_in.balance
    db_account.creditLimit = account_in.creditLimit
    db_account.offset = account_in.offset
    db_account.image = account_in.image

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    # This is crucial for LWW, as the incoming payload's timestamp must be respected if it's the "winner"
    if account_in.updated_at:
        db_account.updatedAt = account_in.updated_at
    # If not provided, SQLAlchemy's onupdate will trigger if other fields changed.
    # If only updatedAt was different and not provided in payload, it means we are keeping the DB version.

    db.add(db_account)
    db.commit()
    db.refresh(db_account)

    # WebSocket notification logic is moved to the service layer.

    return db_account


def delete_account(  # Changed to sync
    db: Session,
    *,
    account_id: str,
) -> Optional[Account]:
    """Deletes an Account by its ID."""
    db_account = get_account(db, account_id=account_id)
    if db_account:
        # Store id before deleting, as it might not be accessible after deletion from session
        deleted_account_id = db_account.id
        db.delete(db_account)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return (
            db_account
        )  # Return the object that was deleted (now detached from session)
    return None


def get_accounts_modified_since(
    db: Session, *, timestamp: datetime
) -> List[Account]:
    """Retrieves all accounts that were created or updated since the given timestamp."""
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(Account).filter(Account.updatedAt >= timestamp).all()
