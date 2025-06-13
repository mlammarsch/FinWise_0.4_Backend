import asyncio
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import WebSocket

from app.models.financial_models import CategoryGroup
from app.websocket.schemas import (
    CategoryGroupPayload,
    DataUpdateNotificationMessage,
    EntityType,
    SyncOperationType,
    DeletePayload,
    ServerEventType
)
from app.websocket.connection_manager import ConnectionManager, manager as websocket_manager_instance
from datetime import datetime


def get_category_group(db: Session, category_group_id: str) -> Optional[CategoryGroup]:
    return db.query(CategoryGroup).filter(CategoryGroup.id == category_group_id).first()


def get_category_groups(db: Session, skip: int = 0, limit: int = 100) -> List[CategoryGroup]:
    return db.query(CategoryGroup).offset(skip).limit(limit).all()


def create_category_group(
    db: Session,
    *,
    category_group_in: CategoryGroupPayload,
) -> CategoryGroup:
    """Creates a new CategoryGroup."""
    db_category_group = CategoryGroup(
        id=category_group_in.id,  # Use the ID from payload
        name=category_group_in.name,
        sortOrder=category_group_in.sortOrder,
        isIncomeGroup=category_group_in.isIncomeGroup,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=category_group_in.updated_at if category_group_in.updated_at else datetime.utcnow()
    )
    db.add(db_category_group)
    db.commit()
    db.refresh(db_category_group)

    # WebSocket notification logic is moved to the service layer.

    return db_category_group


def update_category_group(
    db: Session,
    *,
    db_category_group: CategoryGroup,
    category_group_in: CategoryGroupPayload,
) -> CategoryGroup:
    """Updates an existing CategoryGroup."""
    db_category_group.name = category_group_in.name
    db_category_group.sortOrder = category_group_in.sortOrder
    db_category_group.isIncomeGroup = category_group_in.isIncomeGroup

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    if category_group_in.updated_at:
        db_category_group.updatedAt = category_group_in.updated_at

    db.add(db_category_group)
    db.commit()
    db.refresh(db_category_group)

    # WebSocket notification logic is moved to the service layer.

    return db_category_group


def delete_category_group(
    db: Session,
    *,
    category_group_id: str,
) -> Optional[CategoryGroup]:
    """Deletes a CategoryGroup by its ID."""
    db_category_group = get_category_group(db, category_group_id=category_group_id)
    if db_category_group:
        deleted_category_group_id = db_category_group.id
        db.delete(db_category_group)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return db_category_group  # Return the object that was deleted (now detached from session)
    return None


def get_category_groups_modified_since(db: Session, *, timestamp: datetime) -> List[CategoryGroup]:
    """Retrieves all category groups that were created or updated since the given timestamp."""
    return db.query(CategoryGroup).filter(CategoryGroup.updatedAt >= timestamp).all()
