import asyncio  # Required for running async websocket calls from sync functions if needed, or making functions async
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import WebSocket  # Added for type hinting

from app.models.financial_models import Recipient
from app.websocket.schemas import (
    RecipientPayload,
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


def create_recipient(  # Changed to sync, WebSocket logic moved to service layer
    db: Session,
    *,
    recipient_in: RecipientPayload,
) -> Recipient:
    """Creates a new Recipient."""
    db_recipient = Recipient(
        id=recipient_in.id,
        name=recipient_in.name,
        defaultCategoryId=recipient_in.defaultCategoryId,
        note=recipient_in.note,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=recipient_in.updated_at if recipient_in.updated_at else datetime.utcnow(),
    )
    db.add(db_recipient)
    db.commit()
    db.refresh(db_recipient)

    # WebSocket notification logic is moved to the service layer
    # to handle LWW decisions before notifying.

    return db_recipient


def get_recipient(db: Session, *, recipient_id: str) -> Optional[Recipient]:
    """Retrieves a Recipient by its ID."""
    return db.query(Recipient).filter(Recipient.id == recipient_id).first()


def get_recipients(db: Session, skip: int = 0, limit: int = 100) -> List[Recipient]:
    """Retrieves a list of Recipients."""
    return db.query(Recipient).offset(skip).limit(limit).all()


def update_recipient(  # Changed to sync
    db: Session,
    *,
    db_recipient: Recipient,
    recipient_in: RecipientPayload,
) -> Recipient:
    """Updates an existing Recipient."""
    db_recipient.name = recipient_in.name
    db_recipient.defaultCategoryId = recipient_in.defaultCategoryId
    db_recipient.note = recipient_in.note

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    # This is crucial for LWW, as the incoming payload's timestamp must be respected if it's the "winner"
    if recipient_in.updated_at:
        db_recipient.updatedAt = recipient_in.updated_at
    # If not provided, SQLAlchemy's onupdate will trigger if other fields changed.
    # If only updatedAt was different and not provided in payload, it means we are keeping the DB version.

    db.add(db_recipient)
    db.commit()
    db.refresh(db_recipient)

    # WebSocket notification logic is moved to the service layer.

    return db_recipient


def delete_recipient(  # Changed to sync
    db: Session,
    *,
    recipient_id: str,
) -> Optional[Recipient]:
    """Deletes a Recipient by its ID."""
    db_recipient = get_recipient(db, recipient_id=recipient_id)
    if db_recipient:
        # Store id before deleting, as it might not be accessible after deletion from session
        deleted_recipient_id = db_recipient.id
        db.delete(db_recipient)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return (
            db_recipient
        )  # Return the object that was deleted (now detached from session)
    return None


def get_recipients_modified_since(
    db: Session, *, timestamp: datetime
) -> List[Recipient]:
    """Retrieves all recipients that were created or updated since the given timestamp."""
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(Recipient).filter(Recipient.updatedAt >= timestamp).all()
