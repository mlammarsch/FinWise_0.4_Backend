from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class AccountGroupBase(SQLModel):
    name: str = Field(index=True)
    description: Optional[str] = None
    # tenant_id wird in der konkreten Tabelle AccountGroup hinzugefügt


class AccountGroup(AccountGroupBase, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True, nullable=False)


class AccountGroupCreate(AccountGroupBase):
    pass


class AccountGroupRead(AccountGroupBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    tenant_id: UUID


class AccountGroupUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    # updated_at wird automatisch gesetzt
