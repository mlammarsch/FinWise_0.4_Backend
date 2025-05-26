from pydantic import BaseModel, EmailStr
import uuid
from datetime import datetime

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

# Schema für Benutzerdaten, die vom Frontend während des Syncs gesendet werden (enthält UUID, KEIN Passwort)
class UserSyncPayload(UserBase):
    uuid: str

# Tenant Schemas
class TenantBase(BaseModel):
    name: str

class TenantCreate(TenantBase):
    user_id: str

class Tenant(TenantBase):
    uuid: str
    user_id: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        orm_mode = True
