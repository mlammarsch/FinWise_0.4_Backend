from sqlalchemy.orm import Session
from typing import List, Optional, Generic, TypeVar
from datetime import datetime

from app.models.financial_models import Transaction, Recipient
from app.models import schemas
from app.utils.logger import infoLog, errorLog, debugLog

MODULE_NAME = "crud_transaction"

# DEBUG: Add logging to diagnose the Generic type issue
print(f"DEBUG {MODULE_NAME}: Importing Generic types...")

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Base CRUD class with common operations."""

    def __init__(self, model: ModelType):
        self.model = model
        print(f"DEBUG {MODULE_NAME}: CRUDBase initialized with model: {model}")

class CRUDTransaction(CRUDBase[Transaction, schemas.TransactionCreate, schemas.TransactionUpdate]):
    """CRUD operations for Transaction with recipientId handling."""

    def create_with_tenant(
        self,
        db: Session,
        *,
        obj_in: schemas.TransactionCreate,
        tenant_id: str
    ) -> Transaction:
        """Creates a new Transaction with tenant context and recipientId handling."""

        # Handle recipientId and payee field logic
        payee_value = obj_in.payee
        if obj_in.recipient_id:
            # If recipientId is provided, lookup the recipient name for payee
            recipient = db.query(Recipient).filter(Recipient.id == obj_in.recipient_id).first()
            if recipient:
                payee_value = recipient.name
                debugLog(MODULE_NAME, f"Set payee to recipient name: {payee_value}", details={"recipientId": obj_in.recipient_id})
            else:
                errorLog(MODULE_NAME, f"Recipient not found for ID: {obj_in.recipient_id}")

        db_transaction = Transaction(
            id=obj_in.id,
            accountId=obj_in.accountId,
            categoryId=obj_in.categoryId,
            date=obj_in.date,
            valueDate=obj_in.valueDate,
            amount=round(obj_in.amount, 2),  # Rundung auf 2 Dezimalstellen
            description=obj_in.description or "",
            note=obj_in.note,
            tagIds=obj_in.tagIds,
            type=obj_in.type,
            runningBalance=round(obj_in.runningBalance, 2),  # Rundung auf 2 Dezimalstellen
            counterTransactionId=obj_in.counterTransactionId,
            planningTransactionId=obj_in.planningTransactionId,
            isReconciliation=obj_in.isReconciliation or False,
            isCategoryTransfer=obj_in.isCategoryTransfer or False,
            transferToAccountId=obj_in.transferToAccountId,
            reconciled=obj_in.reconciled or False,
            toCategoryId=obj_in.toCategoryId,
            payee=payee_value,
            recipientId=obj_in.recipient_id,  # Store the recipientId
            createdAt=obj_in.createdAt or datetime.utcnow(),  # Verwende createdAt aus Payload falls vorhanden
            updatedAt=obj_in.updatedAt or datetime.utcnow(),  # Korrigiert: camelCase
        )

        db.add(db_transaction)
        db.commit()
        db.refresh(db_transaction)

        infoLog(MODULE_NAME, f"Created Transaction {db_transaction.id} with recipientId: {obj_in.recipient_id}")
        return db_transaction

    def update(
        self,
        db: Session,
        *,
        db_obj: Transaction,
        obj_in: schemas.TransactionUpdate
    ) -> Transaction:
        """Updates an existing Transaction with recipientId handling."""

        # Handle recipientId and payee field logic
        payee_value = obj_in.payee
        if obj_in.recipient_id:
            # If recipientId is provided, lookup the recipient name for payee
            recipient = db.query(Recipient).filter(Recipient.id == obj_in.recipient_id).first()
            if recipient:
                payee_value = recipient.name
                debugLog(MODULE_NAME, f"Updated payee to recipient name: {payee_value}", details={"recipientId": obj_in.recipient_id})
            else:
                errorLog(MODULE_NAME, f"Recipient not found for ID: {obj_in.recipient_id}")

        # Update all fields
        db_obj.accountId = obj_in.accountId
        db_obj.categoryId = obj_in.categoryId
        db_obj.date = obj_in.date
        db_obj.valueDate = obj_in.valueDate
        db_obj.amount = round(obj_in.amount, 2)  # Rundung auf 2 Dezimalstellen
        db_obj.description = obj_in.description or ""
        db_obj.note = obj_in.note
        db_obj.tagIds = obj_in.tagIds
        db_obj.type = obj_in.type
        db_obj.runningBalance = round(obj_in.runningBalance, 2)  # Rundung auf 2 Dezimalstellen
        db_obj.counterTransactionId = obj_in.counterTransactionId
        db_obj.planningTransactionId = obj_in.planningTransactionId
        db_obj.isReconciliation = obj_in.isReconciliation or False
        db_obj.isCategoryTransfer = obj_in.isCategoryTransfer or False
        db_obj.transferToAccountId = obj_in.transferToAccountId
        db_obj.reconciled = obj_in.reconciled or False
        db_obj.toCategoryId = obj_in.toCategoryId
        db_obj.payee = payee_value
        db_obj.recipientId = obj_in.recipient_id  # Update the recipientId

        # Explicitly set updatedAt from payload if provided for LWW conflict resolution
        if obj_in.updatedAt:
            db_obj.updatedAt = obj_in.updatedAt
        else:
            db_obj.updatedAt = datetime.utcnow()

        db.commit()
        db.refresh(db_obj)

        infoLog(MODULE_NAME, f"Updated Transaction {db_obj.id} with recipientId: {obj_in.recipient_id}")
        return db_obj

    def get(self, db: Session, id: str) -> Optional[Transaction]:
        """Retrieves a Transaction by ID."""
        return db.query(Transaction).filter(Transaction.id == id).first()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 1000) -> List[Transaction]:
        """Retrieves all Transactions with optional pagination."""
        return db.query(Transaction).offset(skip).limit(limit).all()

    def delete(self, db: Session, *, id: str) -> Optional[Transaction]:
        """Deletes a Transaction by ID."""
        db_transaction = db.query(Transaction).filter(Transaction.id == id).first()
        if db_transaction:
            db.delete(db_transaction)
            db.commit()
            infoLog(MODULE_NAME, f"Deleted Transaction {id}")
            return db_transaction
        else:
            errorLog(MODULE_NAME, f"Transaction {id} not found for deletion")
            return None

    def get_transactions_modified_since(
        self,
        db: Session,
        *,
        timestamp: datetime
    ) -> List[Transaction]:
        """Retrieves all transactions that were created or updated since the given timestamp."""
        return db.query(Transaction).filter(Transaction.updatedAt >= timestamp).all()

# Create instance of the CRUD class
crud_transaction = CRUDTransaction(Transaction)

# Export functions for compatibility with __init__.py imports
def create_transaction(db: Session, *, obj_in: schemas.TransactionCreate, tenant_id: str) -> Transaction:
    """Wrapper function for create_with_tenant."""
    return crud_transaction.create_with_tenant(db, obj_in=obj_in, tenant_id=tenant_id)

def get_transaction(db: Session, id: str) -> Optional[Transaction]:
    """Wrapper function for get."""
    return crud_transaction.get(db, id=id)

def get_multi(db: Session, *, skip: int = 0, limit: int = 1000) -> List[Transaction]:
    """Wrapper function for get_multi."""
    return crud_transaction.get_multi(db, skip=skip, limit=limit)

def get_transactions(db: Session, *, skip: int = 0, limit: int = 1000) -> List[Transaction]:
    """Wrapper function for get_multi."""
    return crud_transaction.get_multi(db, skip=skip, limit=limit)

def update_transaction(db: Session, *, db_obj: Transaction, obj_in: schemas.TransactionUpdate) -> Transaction:
    """Wrapper function for update."""
    return crud_transaction.update(db, db_obj=db_obj, obj_in=obj_in)

def delete_transaction(db: Session, *, id: str) -> Optional[Transaction]:
    """Wrapper function for delete."""
    return crud_transaction.delete(db, id=id)

def get_transactions_modified_since(db: Session, *, timestamp: datetime) -> List[Transaction]:
    """Wrapper function for get_transactions_modified_since."""
    return crud_transaction.get_transactions_modified_since(db, timestamp=timestamp)
