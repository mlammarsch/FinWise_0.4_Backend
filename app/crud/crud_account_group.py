from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models.account_group import AccountGroup, AccountGroupCreate, AccountGroupUpdate


def create_account_group(
    db: Session, *, account_group_in: AccountGroupCreate, tenant_id: UUID
) -> AccountGroup:
    db_account_group = AccountGroup.model_validate(
        account_group_in, update={"tenant_id": tenant_id}
    )
    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)
    return db_account_group


def get_account_group(
    db: Session, *, account_group_id: UUID, tenant_id: UUID
) -> Optional[AccountGroup]:
    return db.exec(
        select(AccountGroup).where(
            AccountGroup.id == account_group_id, AccountGroup.tenant_id == tenant_id
        )
    ).first()


def get_account_groups(
    db: Session, *, tenant_id: UUID, skip: int = 0, limit: int = 100
) -> List[AccountGroup]:
    return db.exec(
        select(AccountGroup)
        .where(AccountGroup.tenant_id == tenant_id)
        .offset(skip)
        .limit(limit)
    ).all()


def update_account_group(
    db: Session, *, db_account_group: AccountGroup, account_group_in: AccountGroupUpdate
) -> AccountGroup:
    account_group_data = account_group_in.model_dump(exclude_unset=True)
    for key, value in account_group_data.items():
        setattr(db_account_group, key, value)
    db_account_group.updated_at = datetime.utcnow()
    db.add(db_account_group)
    db.commit()
    db.refresh(db_account_group)
    return db_account_group


def delete_account_group(
    db: Session, *, db_account_group: AccountGroup
) -> AccountGroup:
    db.delete(db_account_group)
    db.commit()
    return db_account_group


def get_account_groups_modified_since(
    db: Session, *, tenant_id: UUID, timestamp: datetime
) -> List[AccountGroup]:
    """
    Ruft alle Kontogruppen ab, die seit dem gegebenen Zeitstempel für den Mandanten
    erstellt oder aktualisiert wurden.
    """
    return db.exec(
        select(AccountGroup)
        .where(AccountGroup.tenant_id == tenant_id)
        .where(AccountGroup.updated_at >= timestamp)
    ).all()
