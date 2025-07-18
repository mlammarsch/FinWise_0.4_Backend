import asyncio  # Required for running async websocket calls from sync functions if needed, or making functions async
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import WebSocket  # Added for type hinting

from app.models.financial_models import PlanningTransaction
from app.websocket.schemas import (
    PlanningTransactionPayload,
    DataUpdateNotificationMessage,
    EntityType,
    SyncOperationType,
    DeletePayload,
    ServerEventType,
)
from app.websocket.connection_manager import (
    ConnectionManager,
    manager as websocket_manager_instance,
)  # Use the global manager instance


def create_planning_transaction(  # Changed to sync, WebSocket logic moved to service layer
    db: Session,
    *,
    planning_transaction_in: PlanningTransactionPayload,
) -> PlanningTransaction:
    """Creates a new PlanningTransaction."""

    db_planning_transaction = PlanningTransaction(
        id=planning_transaction_in.id,
        name=planning_transaction_in.name,
        accountId=planning_transaction_in.accountId,
        categoryId=planning_transaction_in.categoryId,
        tagIds=planning_transaction_in.tagIds,
        recipientId=planning_transaction_in.recipient_id,
        amount=planning_transaction_in.amount,
        amountType=planning_transaction_in.amountType,
        approximateAmount=planning_transaction_in.approximateAmount,
        minAmount=planning_transaction_in.minAmount,
        maxAmount=planning_transaction_in.maxAmount,
        note=planning_transaction_in.note,
        startDate=planning_transaction_in.startDate,
        valueDate=planning_transaction_in.valueDate,
        endDate=planning_transaction_in.endDate,
        recurrencePattern=planning_transaction_in.recurrencePattern,
        recurrenceCount=planning_transaction_in.recurrenceCount,
        recurrenceEndType=planning_transaction_in.recurrenceEndType,
        executionDay=planning_transaction_in.executionDay,
        weekendHandling=planning_transaction_in.weekendHandling,
        transactionType=planning_transaction_in.transactionType,
        counterPlanningTransactionId=planning_transaction_in.counterPlanningTransactionId,
        transferToAccountId=planning_transaction_in.transferToAccountId,
        transferToCategoryId=planning_transaction_in.transferToCategoryId,
        isActive=planning_transaction_in.isActive,
        forecastOnly=planning_transaction_in.forecastOnly,
        autoExecute=planning_transaction_in.autoExecute,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=planning_transaction_in.updated_at if planning_transaction_in.updated_at else datetime.utcnow(),
    )
    db.add(db_planning_transaction)
    db.commit()
    db.refresh(db_planning_transaction)
    return db_planning_transaction


def get_planning_transaction(db: Session, planning_transaction_id: str) -> Optional[PlanningTransaction]:
    """Retrieves a PlanningTransaction by ID."""
    return db.query(PlanningTransaction).filter(PlanningTransaction.id == planning_transaction_id).first()


def get_planning_transactions(db: Session, skip: int = 0, limit: int = 100) -> List[PlanningTransaction]:
    """Retrieves all PlanningTransactions with optional pagination."""
    return db.query(PlanningTransaction).offset(skip).limit(limit).all()


def update_planning_transaction(
    db: Session, *, db_planning_transaction: PlanningTransaction, planning_transaction_in: PlanningTransactionPayload
) -> PlanningTransaction:
    """Updates an existing PlanningTransaction."""

    # Update all fields from the payload
    db_planning_transaction.name = planning_transaction_in.name
    db_planning_transaction.accountId = planning_transaction_in.accountId
    db_planning_transaction.categoryId = planning_transaction_in.categoryId
    db_planning_transaction.tagIds = planning_transaction_in.tagIds
    db_planning_transaction.recipientId = planning_transaction_in.recipient_id
    db_planning_transaction.amount = planning_transaction_in.amount
    db_planning_transaction.amountType = planning_transaction_in.amountType
    db_planning_transaction.approximateAmount = planning_transaction_in.approximateAmount
    db_planning_transaction.minAmount = planning_transaction_in.minAmount
    db_planning_transaction.maxAmount = planning_transaction_in.maxAmount
    db_planning_transaction.note = planning_transaction_in.note
    db_planning_transaction.startDate = planning_transaction_in.startDate
    db_planning_transaction.valueDate = planning_transaction_in.valueDate
    db_planning_transaction.endDate = planning_transaction_in.endDate
    db_planning_transaction.recurrencePattern = planning_transaction_in.recurrencePattern
    db_planning_transaction.recurrenceCount = planning_transaction_in.recurrenceCount
    db_planning_transaction.recurrenceEndType = planning_transaction_in.recurrenceEndType
    db_planning_transaction.executionDay = planning_transaction_in.executionDay
    db_planning_transaction.weekendHandling = planning_transaction_in.weekendHandling
    db_planning_transaction.transactionType = planning_transaction_in.transactionType
    db_planning_transaction.counterPlanningTransactionId = planning_transaction_in.counterPlanningTransactionId
    db_planning_transaction.transferToAccountId = planning_transaction_in.transferToAccountId
    db_planning_transaction.transferToCategoryId = planning_transaction_in.transferToCategoryId
    db_planning_transaction.isActive = planning_transaction_in.isActive
    db_planning_transaction.forecastOnly = planning_transaction_in.forecastOnly
    db_planning_transaction.autoExecute = planning_transaction_in.autoExecute

    # Update timestamp
    db_planning_transaction.updatedAt = planning_transaction_in.updated_at if planning_transaction_in.updated_at else datetime.utcnow()

    db.add(db_planning_transaction)
    db.commit()
    db.refresh(db_planning_transaction)
    return db_planning_transaction


def delete_planning_transaction(db: Session, *, planning_transaction_id: str) -> Optional[PlanningTransaction]:
    """Deletes a PlanningTransaction by ID."""
    db_planning_transaction = db.query(PlanningTransaction).filter(PlanningTransaction.id == planning_transaction_id).first()
    if db_planning_transaction:
        db.delete(db_planning_transaction)
        db.commit()
        return db_planning_transaction
    return None


def get_planning_transactions_modified_since(
    db: Session, *, timestamp: datetime
) -> List[PlanningTransaction]:
    """Retrieves all planning transactions that were created or updated since the given timestamp."""
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(PlanningTransaction).filter(PlanningTransaction.updatedAt >= timestamp).all()
