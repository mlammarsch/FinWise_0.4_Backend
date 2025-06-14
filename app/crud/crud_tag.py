import asyncio  # Required for running async websocket calls from sync functions if needed, or making functions async
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import WebSocket  # Added for type hinting

from app.models.financial_models import Tag
from app.websocket.schemas import (
    TagPayload,
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


def create_tag(  # Changed to sync, WebSocket logic moved to service layer
    db: Session,
    *,
    tag_in: TagPayload,
) -> Tag:
    """Creates a new Tag."""
    db_tag = Tag(
        id=tag_in.id,
        name=tag_in.name,
        parentTagId=tag_in.parentTagId,
        color=tag_in.color,
        icon=tag_in.icon,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=tag_in.updated_at if tag_in.updated_at else datetime.utcnow(),
    )
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)

    # WebSocket notification logic is moved to the service layer
    # to handle LWW decisions before notifying.

    return db_tag


def get_tag(db: Session, *, tag_id: str) -> Optional[Tag]:
    """Retrieves a Tag by its ID."""
    return db.query(Tag).filter(Tag.id == tag_id).first()


def get_tags(db: Session, skip: int = 0, limit: int = 100) -> List[Tag]:
    """Retrieves a list of Tags."""
    return db.query(Tag).offset(skip).limit(limit).all()


def update_tag(  # Changed to sync
    db: Session,
    *,
    db_tag: Tag,
    tag_in: TagPayload,
) -> Tag:
    """Updates an existing Tag."""
    db_tag.name = tag_in.name
    db_tag.parentTagId = tag_in.parentTagId
    db_tag.color = tag_in.color
    db_tag.icon = tag_in.icon

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    # This is crucial for LWW, as the incoming payload's timestamp must be respected if it's the "winner"
    if tag_in.updated_at:
        db_tag.updatedAt = tag_in.updated_at
    # If not provided, SQLAlchemy's onupdate will trigger if other fields changed.
    # If only updatedAt was different and not provided in payload, it means we are keeping the DB version.

    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)

    # WebSocket notification logic is moved to the service layer.

    return db_tag


def delete_tag(  # Changed to sync
    db: Session,
    *,
    tag_id: str,
) -> Optional[Tag]:
    """Deletes a Tag by its ID."""
    db_tag = get_tag(db, tag_id=tag_id)
    if db_tag:
        # Store id before deleting, as it might not be accessible after deletion from session
        deleted_tag_id = db_tag.id
        db.delete(db_tag)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return (
            db_tag
        )  # Return the object that was deleted (now detached from session)
    return None


def get_tags_modified_since(
    db: Session, *, timestamp: datetime
) -> List[Tag]:
    """Retrieves all tags that were created or updated since the given timestamp."""
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(Tag).filter(Tag.updatedAt >= timestamp).all()
