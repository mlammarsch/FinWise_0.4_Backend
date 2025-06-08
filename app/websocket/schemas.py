from pydantic import BaseModel
from typing import Literal, Union, Optional, Dict, Any
from enum import Enum
from pydantic import Field, validator
from uuid import UUID
import datetime # Python's datetime, not Pydantic's

class BackendStatusMessage(BaseModel):
    """
    Represents a message indicating the backend's status.
    """
    type: Literal["status"] = "status"
    status: str  # e.g., "online", "maintenance"

# Enum definitions based on frontend types
class EntityType(str, Enum):
    ACCOUNT = "Account"
    ACCOUNT_GROUP = "AccountGroup"

class SyncOperationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class AccountType(str, Enum):
    CHECKING = 'CHECKING'
    SAVINGS = 'SAVINGS'
    CREDIT = 'CREDIT'
    CASH = 'CASH'

# Pydantic models for payload data
class AccountPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    description: Optional[str] = None
    note: Optional[str] = None
    accountType: AccountType
    isActive: bool
    isOfflineBudget: bool
    accountGroupId: str # UUID as string from frontend
    sortOrder: int
    iban: Optional[str] = None
    balance: float # Assuming balance can be float
    creditLimit: Optional[float] = None # Assuming creditLimit can be float
    offset: int # Assuming offset is an integer
    image: Optional[str] = None

    class Config:
        use_enum_values = True

class AccountGroupPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    sortOrder: int
    image: Optional[str] = None

    class Config:
        use_enum_values = True

# For DELETE operation, payload might just contain the ID or be null
class DeletePayload(BaseModel):
    id: str

# Union type for the payload based on entityType and operationType
SyncEntryDataPayload = Union[AccountPayload, AccountGroupPayload, DeletePayload, None]

class SyncQueueEntry(BaseModel):
    id: str # UUID of the queue entry itself
    tenantId: str # UUID of the tenant
    entityType: EntityType
    entityId: str # UUID of the entity being synced
    operationType: SyncOperationType
    payload: Optional[SyncEntryDataPayload] = None # Payload can be null for DELETE
    timestamp: int # Unix timestamp
    # status: SyncStatus # Status from frontend, not strictly needed for backend processing validation
                        # but good to be aware of. We'll define our own status for responses.

    @validator('entityType', pre=True, always=True)
    def ensure_entity_type_is_enum(cls, v):
        if isinstance(v, str):
            try:
                return EntityType(v)
            except ValueError:
                raise ValueError(f"Ungültiger Wert für EntityType: {v}")
        if isinstance(v, EntityType):
            return v
        raise TypeError(f"Ungültiger Typ für EntityType: {type(v)}")

    @validator('operationType', pre=True, always=True)
    def ensure_operation_type_is_enum(cls, v):
        if isinstance(v, str):
            try:
                return SyncOperationType(v)
            except ValueError:
                raise ValueError(f"Ungültiger Wert für SyncOperationType: {v}")
        if isinstance(v, SyncOperationType):
            return v
        raise TypeError(f"Ungültiger Typ für SyncOperationType: {type(v)}")

    @validator('payload', pre=True, always=True)
    def validate_payload_based_on_operation(cls, v, values):
        op_type = values.get('operationType')
        entity_type = values.get('entityType')

        if op_type == SyncOperationType.DELETE:
            if v is not None and not isinstance(v, DeletePayload):
                 # Allow it to be None or a dict that can be parsed into DeletePayload
                if isinstance(v, dict) and 'id' in v:
                    return DeletePayload(**v)
                # If it's already a DeletePayload instance, it's fine
                elif isinstance(v, DeletePayload):
                    return v
                # Otherwise, if it's not None and not a valid dict for DeletePayload, it's an error
                # For now, we allow None for delete, or a dict with just 'id'
                # raise ValueError("Payload must be a DeletePayload or None for DELETE operation")
            return v # Can be None or DeletePayload
        elif op_type in [SyncOperationType.CREATE, SyncOperationType.UPDATE]:
            if v is None:
                raise ValueError("Payload cannot be null for CREATE or UPDATE operations")
            if entity_type == EntityType.ACCOUNT:
                if not isinstance(v, AccountPayload):
                    if isinstance(v, dict):
                        return AccountPayload(**v)
                    raise ValueError("Payload must be AccountPayload for Account entity type")
            elif entity_type == EntityType.ACCOUNT_GROUP:
                if not isinstance(v, AccountGroupPayload):
                    if isinstance(v, dict):
                        return AccountGroupPayload(**v)
                    raise ValueError("Payload must be AccountGroupPayload for AccountGroup entity type")
        return v

    class Config:
        use_enum_values = True
        extra = 'ignore' # Ignore fields like 'status' from frontend if sent

class ProcessSyncEntryMessage(BaseModel):
    type: Literal["process_sync_entry"] = "process_sync_entry"
    payload: SyncQueueEntry


# Schemas for Server-to-Client WebSocket messages

class ServerEventType(str, Enum):
    """
    Defines the type of event being sent from the server to the client.
    """
    DATA_UPDATE = "data_update"
    # Future event types can be added here, e.g., ERROR_NOTIFICATION, GENERAL_MESSAGE


# The 'data' field for a DATA_UPDATE notification message.
# It can be a full Account or AccountGroup payload for create/update operations,
# or a DeletePayload (containing just the ID) for delete operations.
NotificationDataPayload = Union[AccountPayload, AccountGroupPayload, DeletePayload]


class DataUpdateNotificationMessage(BaseModel):
    """
    Pydantic model for WebSocket messages sent from the server to clients
    when data (Account, AccountGroup) is created, updated, or deleted.
    """
    event_type: Literal[ServerEventType.DATA_UPDATE] = ServerEventType.DATA_UPDATE
    tenant_id: str  # UUID of the tenant as a string
    entity_type: EntityType
    operation_type: SyncOperationType
    data: NotificationDataPayload

    @validator('data', pre=True, always=True)
    def validate_data_based_on_operation_and_entity(cls, v, values):
        """
        Validates that the 'data' payload matches the 'operation_type' and 'entity_type'.
        - For DELETE: 'data' must be DeletePayload.
        - For CREATE/UPDATE of Account: 'data' must be AccountPayload.
        - For CREATE/UPDATE of AccountGroup: 'data' must be AccountGroupPayload.
        """
        op_type = values.get('operation_type')
        entity_type = values.get('entity_type')

        if op_type == SyncOperationType.DELETE:
            if not isinstance(v, DeletePayload):
                # Allow a dict that can be parsed into DeletePayload
                if isinstance(v, dict) and 'id' in v:
                    return DeletePayload(**v)
                # If it's already a DeletePayload instance, it's fine
                elif isinstance(v, DeletePayload):
                    return v
                raise ValueError(
                    f"For DELETE operation, 'data' must be a DeletePayload or a dict with 'id'. Got: {type(v)}"
                )
        elif op_type in [SyncOperationType.CREATE, SyncOperationType.UPDATE]:
            if entity_type == EntityType.ACCOUNT:
                if not isinstance(v, AccountPayload):
                    if isinstance(v, dict):
                        return AccountPayload(**v)
                    raise ValueError(
                        f"For Account entity with {op_type.value} operation, 'data' must be AccountPayload. Got: {type(v)}"
                    )
            elif entity_type == EntityType.ACCOUNT_GROUP:
                if not isinstance(v, AccountGroupPayload):
                    if isinstance(v, dict):
                        return AccountGroupPayload(**v)
                    raise ValueError(
                        f"For AccountGroup entity with {op_type.value} operation, 'data' must be AccountGroupPayload. Got: {type(v)}"
                    )
            else:
                # This case should ideally not be reached if EntityType is exhaustive for operations
                raise ValueError(f"Unsupported entity_type '{entity_type}' for CREATE/UPDATE operation.")
        else:
            # This case should ideally not be reached if SyncOperationType is exhaustive
            raise ValueError(f"Unsupported operation_type: {op_type}")
        return v

    class Config:
        use_enum_values = True
        # If you want to allow arbitrary types for 'data' initially and validate later,
        # you might need to adjust Pydantic's config or the validator.
        # However, for strong typing, this structure is preferred.

# Optional: A Union of all possible messages the server might send to the client.
# This can be useful for type hinting in the ConnectionManager or endpoint.
# ServerToClientMessage = Union[DataUpdateNotificationMessage, BackendStatusMessage]
# For now, we'll handle DataUpdateNotificationMessage specifically.
