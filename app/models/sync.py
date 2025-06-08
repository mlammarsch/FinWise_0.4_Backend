from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from .account import AccountRead
from .account_group import AccountGroupRead


class SyncOperationType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class SyncEntityType(str, Enum):
    ACCOUNT = "Account"
    ACCOUNT_GROUP = "AccountGroup"
    # Weitere Entitätstypen können hier hinzugefügt werden


class SyncQueueItemIn(BaseModel):
    id: Optional[str]
    entity_type: SyncEntityType
    entity_id: UUID
    operation: SyncOperationType
    payload: Dict[str, Any]
    created_at: datetime
    # updated_at aus dem Payload wird für LWW verwendet

    class Config:
        use_enum_values = True


class SyncPushRequest(BaseModel):
    changes: List[SyncQueueItemIn]


class SyncPushResponseItem(BaseModel):
    frontend_sync_queue_item_id: Optional[str] = None
    entity_id: UUID
    entity_type: SyncEntityType
    success: bool
    message: Optional[str] = None
    error_code: Optional[str] = None
    updated_entity: Optional[Union[AccountRead, AccountGroupRead]] = None


class SyncPushResponse(BaseModel):
    results: List[SyncPushResponseItem]


class SyncPullResponse(BaseModel):
    new_or_updated: List[Union[AccountRead, AccountGroupRead]]
    deleted_ids: List[UUID]
    new_last_synced_timestamp: datetime
