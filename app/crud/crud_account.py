from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models.account import Account, AccountCreate, AccountUpdate


def create_account(db: Session, *, account_in: AccountCreate, tenant_id: UUID) -> Account:
    db_account = Account.model_validate(account_in, update={"tenant_id": tenant_id})
    # created_at und updated_at werden durch default_factory gesetzt
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def get_account(db: Session, *, account_id: UUID, tenant_id: UUID) -> Optional[Account]:
    return db.exec(
        select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
    ).first()


def get_accounts(
    db: Session, *, tenant_id: UUID, skip: int = 0, limit: int = 100
) -> List[Account]:
    return db.exec(
        select(Account).where(Account.tenant_id == tenant_id).offset(skip).limit(limit)
    ).all()


def update_account(
    db: Session, *, db_account: Account, account_in: AccountUpdate
) -> Account:
    account_data = account_in.model_dump(exclude_unset=True)
    for key, value in account_data.items():
        setattr(db_account, key, value)
    db_account.updated_at = datetime.utcnow()
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def delete_account(db: Session, *, db_account: Account) -> Account:
    # Für Soft-Delete müsste hier ein 'deleted_at' Feld gesetzt werden.
    # Aktuell: Hard-Delete
    db.delete(db_account)
    db.commit()
    # Rückgabe des gelöschten Objekts (oder nur ID/Status) kann variieren.
    # Da es gelöscht ist, kann db.refresh(db_account) fehlschlagen.
    # Wir geben das Objekt zurück, wie es vor dem Löschen war (ohne Refresh).
    return db_account


def get_accounts_modified_since(
    db: Session, *, tenant_id: UUID, timestamp: datetime
) -> List[Account]:
    """
    Ruft alle Konten ab, die seit dem gegebenen Zeitstempel für den Mandanten
    erstellt oder aktualisiert wurden.
    """
    return db.exec(
        select(Account)
        .where(Account.tenant_id == tenant_id)
        .where(Account.updated_at >= timestamp) # updated_at >= last_sync für Änderungen und neue
    ).all()
