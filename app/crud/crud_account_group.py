from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID # Keep for potential future use, though IDs are strings now

from app.models.financial_models import AccountGroup
from app.websocket.schemas import AccountGroupPayload # For type hinting create/update data

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

def create_account_group(db: Session, *, account_group_in: AccountGroupPayload) -> AccountGroup:
    """
    Creates a new AccountGroup.
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
    return db_account_group

def update_account_group(
    db: Session, *, db_account_group: AccountGroup, account_group_in: AccountGroupPayload
) -> AccountGroup:
    """
    Updates an existing AccountGroup.
    account_group_in contains all fields for update, not partial.
    """
    db_account_group.name = account_group_in.name
    db_account_group.sortOrder = account_group_in.sortOrder
    db_account_group.image = account_group_in.image
    # updatedAt will be updated by the model's onupdate

    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)
    return db_account_group

def delete_account_group(db: Session, *, account_group_id: str) -> Optional[AccountGroup]:
    """
    Deletes an AccountGroup by its ID.
    Returns the deleted object or None if not found.
    """
    db_account_group = get_account_group(db, account_group_id=account_group_id)
    if db_account_group:
        db.delete(db_account_group)
        db.commit()
    return db_account_group

# Potentially a function to get AccountGroups modified since a certain timestamp,
# similar to what's in crud_account.py, could be added here if needed for sync later.
# def get_account_groups_modified_since(db: Session, *, timestamp: datetime) -> List[AccountGroup]:
#     return db.query(AccountGroup).filter(AccountGroup.updatedAt >= timestamp).all()
