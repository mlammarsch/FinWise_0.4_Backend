from pydantic import BaseModel, EmailStr
import uuid
from datetime import datetime
from decimal import Decimal

# User Schemas
class UserBase(BaseModel):
    name: str
    email: EmailStr

# Schema für die Online-Registrierung (enthält Passwort)
class RegisterUserPayload(UserBase):
    password: str

# Schema für den Online-Login
class LoginPayload(BaseModel):
    username_or_email: str
    password: str

# Schema für die API-Antworten (enthält KEIN Passwort)
class User(UserBase):
    uuid: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True

# Schema für Benutzerdaten, die vom Frontend während des Syncs gesendet werden (enthält UUID, optional Passworthash)
class UserSyncPayload(UserBase):
    uuid: str
    hashed_password: str | None = None

# Tenant Schemas
class TenantBase(BaseModel):
    name: str

class TenantCreate(TenantBase):
    user_id: str
    uuid: str | None = None

class TenantUpdate(BaseModel):
    name: str

class Tenant(TenantBase):
    uuid: str
    user_id: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True

# AccountGroup Schemas
class AccountGroupBase(BaseModel):
    name: str
    sortOrder: int | None = 0
    image: str | None = None

class AccountGroupPayload(AccountGroupBase):
    id: str | None = None
    updated_at: datetime | None = None

class AccountGroupSchema(AccountGroupBase):
    id: str
    createdAt: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Tenant Management Response Schemas
class TenantDeletionResponse(BaseModel):
    message: str
    tenant_id: str
    tenant_name: str
    database_file_deleted: bool

class TenantDatabaseResetResponse(BaseModel):
    message: str
    tenant_id: str

class SyncQueueClearResponse(BaseModel):
    message: str
    tenant_id: str
    entries_cleared: int = 0

# Account Schemas
class AccountBase(BaseModel):
    name: str
    description: str | None = None
    note: str | None = None
    accountType: str
    isActive: bool | None = True
    isOfflineBudget: bool | None = False
    accountGroupId: str
    sortOrder: int | None = 0
    iban: str | None = None
    balance: Decimal | None = Decimal('0.0')
    creditLimit: Decimal | None = Decimal('0.0')
    offset: int | None = 0
    image: str | None = None

class AccountPayload(AccountBase):
    id: str | None = None
    updated_at: datetime | None = None

class AccountSchema(AccountBase):
    id: str
    createdAt: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
