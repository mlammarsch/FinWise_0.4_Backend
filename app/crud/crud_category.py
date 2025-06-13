import asyncio
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import WebSocket

from app.models.financial_models import Category
from app.websocket.schemas import (
    CategoryPayload,
    DataUpdateNotificationMessage,
    EntityType,
    SyncOperationType,
    DeletePayload,
    ServerEventType,
)
from app.websocket.connection_manager import (
    ConnectionManager,
    manager as websocket_manager_instance,
)


def create_category(
    db: Session,
    *,
    category_in: CategoryPayload,
) -> Category:
    """Creates a new Category."""
    db_category = Category(
        id=category_in.id,
        name=category_in.name,
        icon=category_in.icon,
        budgeted=category_in.budgeted,
        activity=category_in.activity,
        available=category_in.available,
        isIncomeCategory=category_in.isIncomeCategory,
        isHidden=category_in.isHidden,
        isActive=category_in.isActive,
        sortOrder=category_in.sortOrder,
        categoryGroupId=category_in.categoryGroupId,
        parentCategoryId=category_in.parentCategoryId,
        isSavingsGoal=category_in.isSavingsGoal,
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=category_in.updated_at if category_in.updated_at else datetime.utcnow(),
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)

    # WebSocket notification logic is moved to the service layer
    # to handle LWW decisions before notifying.

    return db_category


def get_category(db: Session, *, category_id: str) -> Optional[Category]:
    """Retrieves a Category by its ID."""
    return db.query(Category).filter(Category.id == category_id).first()


def get_categories(db: Session, skip: int = 0, limit: int = 100) -> List[Category]:
    """Retrieves a list of Categories."""
    return db.query(Category).offset(skip).limit(limit).all()


def update_category(
    db: Session,
    *,
    db_category: Category,
    category_in: CategoryPayload,
) -> Category:
    """Updates an existing Category."""
    db_category.name = category_in.name
    db_category.icon = category_in.icon
    db_category.budgeted = category_in.budgeted
    db_category.activity = category_in.activity
    db_category.available = category_in.available
    db_category.isIncomeCategory = category_in.isIncomeCategory
    db_category.isHidden = category_in.isHidden
    db_category.isActive = category_in.isActive
    db_category.sortOrder = category_in.sortOrder
    db_category.categoryGroupId = category_in.categoryGroupId
    db_category.parentCategoryId = category_in.parentCategoryId
    db_category.isSavingsGoal = category_in.isSavingsGoal

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    # This is crucial for LWW, as the incoming payload's timestamp must be respected if it's the "winner"
    if category_in.updated_at:
        db_category.updatedAt = category_in.updated_at
    # If not provided, SQLAlchemy's onupdate will trigger if other fields changed.
    # If only updatedAt was different and not provided in payload, it means we are keeping the DB version.

    db.add(db_category)
    db.commit()
    db.refresh(db_category)

    # WebSocket notification logic is moved to the service layer.

    return db_category


def delete_category(
    db: Session,
    *,
    category_id: str,
) -> Optional[Category]:
    """Deletes a Category by its ID."""
    db_category = get_category(db, category_id=category_id)
    if db_category:
        # Store id before deleting, as it might not be accessible after deletion from session
        deleted_category_id = db_category.id
        db.delete(db_category)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return (
            db_category
        )  # Return the object that was deleted (now detached from session)
    return None


def get_categories_modified_since(
    db: Session, *, timestamp: datetime
) -> List[Category]:
    """Retrieves all categories that were created or updated since the given timestamp."""
    return db.query(Category).filter(Category.updatedAt >= timestamp).all()
