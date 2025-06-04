from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session # Changed from sqlmodel import Session
# from uuid import UUID # IDs are now strings

# Use the new SQLAlchemy models and Pydantic schemas
from app.models.financial_models import Account
from app.websocket.schemas import AccountPayload # For type hinting create/update data


def create_account(db: Session, *, account_in: AccountPayload) -> Account:
    """
    Creates a new Account.
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


def update_account(
    db: Session, *, db_account: Account, account_in: AccountPayload
) -> Account:
    """
    Updates an existing Account.
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
    return db_account


def delete_account(db: Session, *, account_id: str) -> Optional[Account]:
    """
    Deletes an Account by its ID.
    Returns the deleted object or None if not found.
    """
    db_account = get_account(db, account_id=account_id)
    if db_account:
        db.delete(db_account)
        db.commit()
    return db_account


def get_accounts_modified_since(
    db: Session, *, timestamp: datetime
) -> List[Account]:
    """
    Retrieves all accounts that were created or updated since the given timestamp.
    """
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(Account).filter(Account.updatedAt >= timestamp).all()
