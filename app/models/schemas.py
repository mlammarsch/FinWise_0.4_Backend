from pydantic import BaseModel, EmailStr
import uuid
from datetime import datetime

# User Schemas
class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str # TODO: Implement password hashing

class User(UserBase):
    uuid: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        orm_mode = True

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
