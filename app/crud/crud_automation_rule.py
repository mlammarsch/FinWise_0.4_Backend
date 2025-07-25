import asyncio  # Required for running async websocket calls from sync functions if needed, or making functions async
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import WebSocket  # Added for type hinting

from app.models.financial_models import AutomationRule
from app.websocket.schemas import (
    AutomationRulePayload,
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


def create_automation_rule(  # Changed to sync, WebSocket logic moved to service layer
    db: Session,
    *,
    automation_rule_in: AutomationRulePayload,
) -> AutomationRule:
    """Creates a new AutomationRule."""
    db_automation_rule = AutomationRule(
        id=automation_rule_in.id,
        name=automation_rule_in.name,
        description=automation_rule_in.description,
        stage=automation_rule_in.stage,
        conditions=automation_rule_in.conditions,
        actions=automation_rule_in.actions,
        priority=automation_rule_in.priority,
        isActive=automation_rule_in.isActive,
        conditionLogic=automation_rule_in.conditionLogic or 'all',
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=automation_rule_in.updated_at if automation_rule_in.updated_at else datetime.utcnow(),
    )
    db.add(db_automation_rule)
    db.commit()
    db.refresh(db_automation_rule)
    return db_automation_rule


def get_automation_rule(db: Session, *, automation_rule_id: str) -> Optional[AutomationRule]:
    """Retrieves an AutomationRule by ID."""
    return db.query(AutomationRule).filter(AutomationRule.id == automation_rule_id).first()


def get_automation_rules(
    db: Session, skip: int = 0, limit: int = 100
) -> List[AutomationRule]:
    """Retrieves all AutomationRules with optional pagination."""
    return db.query(AutomationRule).offset(skip).limit(limit).all()


def update_automation_rule(  # Changed to sync
    db: Session,
    *,
    db_automation_rule: AutomationRule,
    automation_rule_in: AutomationRulePayload,
) -> AutomationRule:
    """Updates an existing AutomationRule."""
    db_automation_rule.name = automation_rule_in.name
    db_automation_rule.description = automation_rule_in.description
    db_automation_rule.stage = automation_rule_in.stage
    db_automation_rule.conditions = automation_rule_in.conditions
    db_automation_rule.actions = automation_rule_in.actions
    db_automation_rule.priority = automation_rule_in.priority
    db_automation_rule.isActive = automation_rule_in.isActive
    db_automation_rule.conditionLogic = automation_rule_in.conditionLogic or 'all'

    # Explicitly set updatedAt from payload if provided, otherwise let onupdate handle it
    # This is crucial for LWW, as the incoming payload's timestamp must be respected if it's the "winner"
    if automation_rule_in.updated_at:
        db_automation_rule.updatedAt = automation_rule_in.updated_at
    # If not provided, SQLAlchemy's onupdate will trigger if other fields changed.
    # If only updatedAt was different and not provided in payload, it means we are keeping the DB version.

    db.add(db_automation_rule)
    db.commit()
    db.refresh(db_automation_rule)

    # WebSocket notification logic is moved to the service layer.

    return db_automation_rule


def delete_automation_rule(  # Changed to sync
    db: Session,
    *,
    automation_rule_id: str,
) -> Optional[AutomationRule]:
    """Deletes an AutomationRule by its ID."""
    db_automation_rule = get_automation_rule(db, automation_rule_id=automation_rule_id)
    if db_automation_rule:
        # Store id before deleting, as it might not be accessible after deletion from session
        deleted_automation_rule_id = db_automation_rule.id
        db.delete(db_automation_rule)
        db.commit()

        # WebSocket notification logic is moved to the service layer.
        return (
            db_automation_rule
        )  # Return the object that was deleted (now detached from session)
    return None


def get_automation_rules_modified_since(
    db: Session, *, timestamp: datetime
) -> List[AutomationRule]:
    """Retrieves all automation rules that were created or updated since the given timestamp."""
    # This function might be useful for a full sync later, but not directly for processing individual queue entries.
    # For now, it's adapted to the new model structure.
    return db.query(AutomationRule).filter(AutomationRule.updatedAt >= timestamp).all()
