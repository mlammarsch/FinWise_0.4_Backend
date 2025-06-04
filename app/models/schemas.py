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
        orm_mode = True

# Schema für Benutzerdaten, die vom Frontend während des Syncs gesendet werden (enthält UUID, optional Passworthash)
class UserSyncPayload(UserBase):
    uuid: str
    hashed_password: str | None = None # Hinzugefügt für den Sync des Passwort-Hashes

# Tenant Schemas
class TenantBase(BaseModel):
    name: str

class TenantCreate(TenantBase):
    user_id: str
    uuid: str | None = None # Füge optionales UUID-Feld hinzu

class Tenant(TenantBase):
    uuid: str
    user_id: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        orm_mode = True

# AccountGroup Schemas
class AccountGroupBase(BaseModel):
    name: str
    sortOrder: int | None = 0
    image: str | None = None

class AccountGroupPayload(AccountGroupBase):
    id: str | None = None # Optional, da es beim Erstellen generiert oder vom Client gesendet werden kann
    updated_at: datetime | None = None # Wird für LWW benötigt

class AccountGroupSchema(AccountGroupBase):
    id: str
    createdAt: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# Account Schemas
class AccountBase(BaseModel):
    name: str
    description: str | None = None
    note: str | None = None
    accountType: str # CHECKING, SAVINGS, etc.
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
    id: str | None = None # Optional
    updated_at: datetime | None = None # Wird für LWW benötigt

class AccountSchema(AccountBase):
    id: str
    createdAt: datetime
    updated_at: datetime
    # account_group: AccountGroupSchema # Optional, falls verschachtelte Daten benötigt werden

    class Config:
        orm_mode = True
