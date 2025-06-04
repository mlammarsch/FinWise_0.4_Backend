from sqlalchemy import Column, String, Boolean, Integer, Float, ForeignKey, DateTime, Text, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID # Using PostgreSQL UUID type for compatibility, can be adapted
import uuid # For default UUID generation
from datetime import datetime

# It's common to have a Base for all models in a specific DB or context.
# If user_tenant_models.py uses a different Base, ensure they don't conflict
# or use a shared Base if appropriate. For tenant-specific tables, this Base is fine.
TenantBase = declarative_base()

class AccountGroup(TenantBase):
    __tablename__ = "account_groups"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())) # Frontend sends string UUIDs
    name = Column(String, nullable=False, index=True)
    sortOrder = Column(Integer, nullable=False, default=0)
    image = Column(String, nullable=True)
    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to Accounts
    accounts = relationship("Account", back_populates="account_group")

    # tenant_id would typically be here if this table was shared across tenants
    # but since these are in tenant-specific DBs, it's implicit.

class Account(TenantBase):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())) # Frontend sends string UUIDs
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    accountType = Column(String, nullable=False) # Matches AccountType enum (CHECKING, SAVINGS, etc.)
    isActive = Column(Boolean, nullable=False, default=True)
    isOfflineBudget = Column(Boolean, nullable=False, default=False)

    accountGroupId = Column(String, ForeignKey("account_groups.id"), nullable=False)
    account_group = relationship("AccountGroup", back_populates="accounts")

    sortOrder = Column(Integer, nullable=False, default=0)
    iban = Column(String, nullable=True)
    balance = Column(Numeric(10, 2), nullable=False, default=0.0)
    creditLimit = Column(Numeric(10, 2), nullable=True, default=0.0)
    offset = Column(Integer, nullable=False, default=0) # Assuming offset is an integer
    image = Column(String, nullable=True)

    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# To ensure these tables are created in the tenant-specific databases,
# this Base's metadata will need to be used when initializing the engine for that tenant.
# For example, TenantBase.metadata.create_all(bind=tenant_engine)
