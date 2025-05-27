from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class AccountBase(SQLModel):
    name: str = Field(index=True)
    description: Optional[str] = None
    account_type: str # z.B. 'checking', 'savings', 'credit_card', 'investment', 'cash'
    currency: str = Field(default="EUR") # ISO 4217 Währungscode
    balance: float = Field(default=0.0)
    is_active: bool = Field(default=True)
    # tenant_id wird in der konkreten Tabelle Account hinzugefügt


class Account(AccountBase, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True, nullable=False)
    # account_group_id: Optional[UUID] = Field(default=None, foreign_key="accountgroup.id", index=True)


class AccountCreate(AccountBase):
    # Felder, die beim Erstellen benötigt werden und nicht in AccountBase sind oder anders validiert werden
    pass


class AccountRead(AccountBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    tenant_id: UUID
    # account_group_id: Optional[UUID]


class AccountUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    account_type: Optional[str] = None
    currency: Optional[str] = None
    balance: Optional[float] = None
    is_active: Optional[bool] = None
    # updated_at wird automatisch gesetzt
    # tenant_id und id sollten nicht direkt aktualisierbar sein über diesen Weg
