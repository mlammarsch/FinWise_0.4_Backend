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
        # createdAt has a default
        # updatedAt will be set explicitly if provided, otherwise model default
        updatedAt=automation_rule_in.updated_at if automation_rule_in.updated_at else datetime.utcnow(),
    )
    db.add(db_automation_rule)
    db.commit()
    db.refresh(db_automation_rule)
    return db_automation_rule


def get_automation_rule(db: Session, automation_rule_id: str) -> Optional[AutomationRule]:
    """Retrieves an AutomationRule by ID."""
    return db.query(AutomationRule).filter(AutomationRule.id == automation_rule_id).first()


def get_automation_rules(
    db: Session, skip: int = 0, limit: int = 100
) -> List[AutomationRule]:
    """Retrieves all AutomationRules with optional pagination."""
    return db.query(AutomationRule).offset(skip).limit(limit).all()


def update_automation_rule(
    db: Session, *, db_obj: AutomationRule, obj_in: AutomationRulePayload
) -> AutomationRule:
    """Updates an existing AutomationRule."""
    # Update fields from the payload
    db_obj.name = obj_in.name
    db_obj.description = obj_in.description
    db_obj.stage = obj_in.stage
    db_obj.conditions = obj_in.conditions
    db_obj.actions = obj_in.actions
    db_obj.priority = obj_in.priority
    db_obj.isActive = obj_in.isActive
    db_obj.updatedAt = obj_in.updated_at if obj_in.updated_at else datetime.utcnow()

    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def delete_automation_rule(db: Session, *, automation_rule_id: str) -> AutomationRule:
    """Deletes an AutomationRule by ID."""
    obj = db.query(AutomationRule).get(automation_rule_id)
    db.delete(obj)
    db.commit()
    return obj
