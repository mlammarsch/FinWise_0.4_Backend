from sqlalchemy import Column, String, Boolean, Integer, Float, ForeignKey, DateTime, Text, Numeric, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID # Using PostgreSQL UUID type for compatibility, can be adapted
import uuid # For default UUID generation
from datetime import datetime, timezone
import enum

# It's common to have a Base for all models in a specific DB or context.
# If user_tenant_models.py uses a different Base, ensure they don't conflict
# or use a shared Base if appropriate. For tenant-specific tables, this Base is fine.
TenantBase = declarative_base()

class AccountType(str, enum.Enum):
    Girokonto = 'giro'
    Tagesgeldkonto = 'tagesgeld'
    Festgeldkonto = 'festgeld'
    Sparkonto = 'spar'
    Kreditkarte = 'kreditkarte'
    Depot = 'depot'
    Bausparvertrag = 'bauspar'
    Darlehenskonto = 'darlehen'
    Geschäftskonto = 'geschaeft'
    Gemeinschaftskonto = 'gemeinschaft'
    Fremdwährungskonto = 'fremdwaehrung'
    Virtuell = 'virtuell'
    Bargeld = 'bar'
    Sonstiges = 'sonstiges'

class AccountGroup(TenantBase):
    __tablename__ = "account_groups"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())) # Frontend sends string UUIDs
    name = Column(String, nullable=False, index=True)
    sortOrder = Column(Integer, nullable=False, default=0)
    logo_path = Column(String, nullable=True)
    # Timestamps
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    accountType = Column(Enum(AccountType, values_callable=lambda obj: [e.value for e in obj]), nullable=False) # Matches AccountType enum
    isActive = Column(Boolean, nullable=False, default=True)
    isOfflineBudget = Column(Boolean, nullable=False, default=False)

    accountGroupId = Column(String, ForeignKey("account_groups.id"), nullable=False)
    account_group = relationship("AccountGroup", back_populates="accounts")

    sortOrder = Column(Integer, nullable=False, default=0)
    iban = Column(String, nullable=True)
    balance = Column(Numeric(10, 2), nullable=False, default=0.0)
    creditLimit = Column(Numeric(10, 2), nullable=True, default=0.0)
    offset = Column(Integer, nullable=False, default=0) # Assuming offset is an integer
    logo_path = Column(String, nullable=True)

    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CategoryGroup(TenantBase):
    __tablename__ = "category_groups"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())) # Frontend sends string UUIDs
    name = Column(String, nullable=False, index=True)
    sortOrder = Column(Integer, nullable=False, default=0)
    isIncomeGroup = Column(Boolean, nullable=False, default=False)
    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to Categories
    categories = relationship("Category", back_populates="category_group")

class Category(TenantBase):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())) # Frontend sends string UUIDs
    name = Column(String, nullable=False, index=True)
    icon = Column(String, nullable=True)
    budgeted = Column(Numeric(10, 2), nullable=False, default=0.0)
    activity = Column(Numeric(10, 2), nullable=False, default=0.0)
    available = Column(Numeric(10, 2), nullable=False, default=0.0)
    isIncomeCategory = Column(Boolean, nullable=False, default=False)
    isHidden = Column(Boolean, nullable=False, default=False)
    isActive = Column(Boolean, nullable=False, default=True)
    sortOrder = Column(Integer, nullable=False, default=0)
    isSavingsGoal = Column(Boolean, nullable=False, default=False)

    categoryGroupId = Column(String, ForeignKey("category_groups.id"), nullable=True)
    category_group = relationship("CategoryGroup", back_populates="categories")

    parentCategoryId = Column(String, ForeignKey("categories.id"), nullable=True)
    parent_category = relationship("Category", remote_side=[id], backref="subcategories")

    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Recipient(TenantBase):
    __tablename__ = "recipients"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    defaultCategoryId = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Tag(TenantBase):
    __tablename__ = "tags"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    parentTagId = Column(String, ForeignKey("tags.id"), nullable=True)
    parent_tag = relationship("Tag", remote_side=[id], backref="subtags")
    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AutomationRule(TenantBase):
    __tablename__ = "automation_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    stage = Column(String, nullable=False, default='DEFAULT') # 'PRE' | 'DEFAULT' | 'POST'
    conditions = Column(JSON, nullable=False, default=list) # Array of RuleCondition objects
    actions = Column(JSON, nullable=False, default=list) # Array of RuleAction objects
    priority = Column(Integer, nullable=False, default=0)
    isActive = Column(Boolean, nullable=False, default=True)
    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PlanningTransaction(TenantBase):
    __tablename__ = "planning_transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    accountId = Column(String, nullable=False, index=True)
    categoryId = Column(String, nullable=True)
    tagIds = Column(JSON, nullable=False, default=list) # Array of tag IDs
    recipientId = Column(String, nullable=True)
    amount = Column(Numeric(10, 2), nullable=False, default=0.0)
    amountType = Column(String, nullable=False, default='EXACT') # 'EXACT', 'APPROXIMATE', 'RANGE'
    approximateAmount = Column(Numeric(10, 2), nullable=True)
    minAmount = Column(Numeric(10, 2), nullable=True)
    maxAmount = Column(Numeric(10, 2), nullable=True)
    note = Column(Text, nullable=True)
    startDate = Column(String, nullable=False) # ISO 8601 date string
    valueDate = Column(String, nullable=True) # ISO 8601 date string
    endDate = Column(String, nullable=True) # ISO 8601 date string
    recurrencePattern = Column(String, nullable=False, default='ONCE') # 'ONCE', 'DAILY', 'WEEKLY', etc.
    recurrenceCount = Column(Integer, nullable=True)
    recurrenceEndType = Column(String, nullable=False, default='NEVER') # 'NEVER', 'COUNT', 'DATE'
    executionDay = Column(Integer, nullable=True)
    weekendHandling = Column(String, nullable=False, default='NONE') # 'NONE', 'BEFORE', 'AFTER'
    transactionType = Column(String, nullable=True) # 'EXPENSE', 'INCOME', 'ACCOUNTTRANSFER', etc.
    counterPlanningTransactionId = Column(String, nullable=True)
    transferToAccountId = Column(String, nullable=True)
    transferToCategoryId = Column(String, nullable=True)
    isActive = Column(Boolean, nullable=False, default=True)
    forecastOnly = Column(Boolean, nullable=False, default=False)
    autoExecute = Column(Boolean, nullable=False, default=False)
    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Transaction(TenantBase):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    accountId = Column(String, nullable=False, index=True)
    categoryId = Column(String, nullable=True)
    date = Column(String, nullable=False, index=True) # ISO 8601 date string
    valueDate = Column(String, nullable=False) # ISO 8601 date string
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    tagIds = Column(JSON, nullable=False, default=list) # Array of tag IDs
    type = Column(String, nullable=False) # TransactionType enum
    runningBalance = Column(Numeric(10, 2), nullable=False, default=0.0)
    counterTransactionId = Column(String, nullable=True)
    planningTransactionId = Column(String, nullable=True)
    isReconciliation = Column(Boolean, nullable=False, default=False)
    isCategoryTransfer = Column(Boolean, nullable=False, default=False)
    transferToAccountId = Column(String, nullable=True)
    reconciled = Column(Boolean, nullable=False, default=False)
    toCategoryId = Column(String, nullable=True)
    payee = Column(String, nullable=True)
    recipientId = Column(String, ForeignKey("recipients.id"), nullable=True)

    # Relationships
    recipient = relationship("Recipient")

    # Timestamps
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# To ensure these tables are created in the tenant-specific databases,
# this Base's metadata will need to be used when initializing the engine for that tenant.
# For example, TenantBase.metadata.create_all(bind=tenant_engine)
