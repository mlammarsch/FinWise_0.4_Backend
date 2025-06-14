from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.models.financial_models import Transaction
from app.websocket.schemas import (
    TransactionPayload,
    DataUpdateNotificationMessage,
    ServerEventType,
    EntityType,
    SyncOperationType,
)
from app.utils.logger import infoLog, errorLog, debugLog

MODULE_NAME = "crud_transaction"

def create_transaction(
    db: Session,
    *,
    transaction_in: TransactionPayload,
) -> Transaction:
    """Creates a new Transaction."""

    db_transaction = Transaction(
        id=transaction_in.id,
        accountId=transaction_in.accountId,
        categoryId=transaction_in.categoryId,
        date=transaction_in.date,
        valueDate=transaction_in.valueDate,
        amount=transaction_in.amount,
        description=transaction_in.description,
        note=transaction_in.note,
        tagIds=transaction_in.tagIds,
        type=transaction_in.type,
        runningBalance=transaction_in.runningBalance,
        counterTransactionId=transaction_in.counterTransactionId,
        planningTransactionId=transaction_in.planningTransactionId,
        isReconciliation=transaction_in.isReconciliation or False,
        isCategoryTransfer=transaction_in.isCategoryTransfer or False,
        transferToAccountId=transaction_in.transferToAccountId,
        reconciled=transaction_in.reconciled or False,
        toCategoryId=transaction_in.toCategoryId,
        payee=transaction_in.payee,
        createdAt=datetime.utcnow(),
        updatedAt=transaction_in.updated_at or datetime.utcnow(),
    )

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)

    infoLog(MODULE_NAME, f"Created Transaction {db_transaction.id}", details=transaction_in.dict())
    return db_transaction


def get_transaction(db: Session, transaction_id: str) -> Optional[Transaction]:
    """Retrieves a Transaction by ID."""
    return db.query(Transaction).filter(Transaction.id == transaction_id).first()


def get_transactions(db: Session, skip: int = 0, limit: int = 1000) -> List[Transaction]:
    """Retrieves all Transactions with optional pagination."""
    return db.query(Transaction).offset(skip).limit(limit).all()

def update_transaction(
    db: Session, *, db_transaction: Transaction, transaction_in: TransactionPayload
) -> Transaction:
    """Updates an existing Transaction."""

    db_transaction.accountId = transaction_in.accountId
    db_transaction.categoryId = transaction_in.categoryId
    db_transaction.date = transaction_in.date
    db_transaction.valueDate = transaction_in.valueDate
    db_transaction.amount = transaction_in.amount
    db_transaction.description = transaction_in.description
    db_transaction.note = transaction_in.note
    db_transaction.tagIds = transaction_in.tagIds
    db_transaction.type = transaction_in.type
    db_transaction.runningBalance = transaction_in.runningBalance
    db_transaction.counterTransactionId = transaction_in.counterTransactionId
    db_transaction.planningTransactionId = transaction_in.planningTransactionId
    db_transaction.isReconciliation = transaction_in.isReconciliation or False
    db_transaction.isCategoryTransfer = transaction_in.isCategoryTransfer or False
    db_transaction.transferToAccountId = transaction_in.transferToAccountId
    db_transaction.reconciled = transaction_in.reconciled or False
    db_transaction.toCategoryId = transaction_in.toCategoryId
    db_transaction.payee = transaction_in.payee
    db_transaction.updatedAt = transaction_in.updated_at or datetime.utcnow()

    db.commit()
    db.refresh(db_transaction)

    infoLog(MODULE_NAME, f"Updated Transaction {db_transaction.id}", details=transaction_in.dict())
    return db_transaction


def delete_transaction(db: Session, *, transaction_id: str) -> Optional[Transaction]:
    """Deletes a Transaction by ID."""
    db_transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if db_transaction:
        db.delete(db_transaction)
        db.commit()
        infoLog(MODULE_NAME, f"Deleted Transaction {transaction_id}")
        return db_transaction
    else:
        errorLog(MODULE_NAME, f"Transaction {transaction_id} not found for deletion")
        return None


def get_transactions_modified_since(
    db: Session, *, timestamp: datetime
) -> List[Transaction]:
    """Retrieves all transactions that were created or updated since the given timestamp."""
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(Transaction).filter(Transaction.updatedAt >= timestamp).all()
