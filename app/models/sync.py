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
    id: Optional[str] # Frontend-ID des SyncQueueItem, nicht die Entitäts-ID
    entity_type: SyncEntityType
    entity_id: UUID # ID der zu synchronisierenden Entität
    operation: SyncOperationType
    payload: Dict[str, Any] # Die eigentlichen Daten der Entität
    created_at: datetime # Zeitstempel der Erstellung des SyncQueueItem im Frontend
    # updated_at aus dem Payload wird für LWW verwendet

    class Config:
        use_enum_values = True


class SyncPushRequest(BaseModel):
    changes: List[SyncQueueItemIn]


class SyncPushResponseItem(BaseModel):
    frontend_sync_queue_item_id: Optional[str] = None # ID des ursprünglichen SyncQueueItem aus dem Request
    entity_id: UUID
    entity_type: SyncEntityType
    success: bool
    message: Optional[str] = None
    error_code: Optional[str] = None # z.B. 'CONFLICT', 'VALIDATION_ERROR', 'DB_ERROR'
    updated_entity: Optional[Union[AccountRead, AccountGroupRead]] = None # Die Entität nach der Verarbeitung im Backend


class SyncPushResponse(BaseModel):
    results: List[SyncPushResponseItem]


class SyncPullResponse(BaseModel):
    new_or_updated: List[Union[AccountRead, AccountGroupRead]] # Vollständige Entitäten
    deleted_ids: List[UUID] # Nur die IDs der gelöschten Entitäten
    new_last_synced_timestamp: datetime
