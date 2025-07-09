from pydantic import BaseModel
from typing import Literal, Union, Optional, Dict, Any
from enum import Enum
from pydantic import Field, validator
from uuid import UUID
import datetime # Python's datetime, not Pydantic's
import logging # Standard-Logging als Fallback
try:
    from app.utils.logger import app_logger as logger
except ImportError:
    logger = logging.getLogger(__name__)
    if not logger.hasHandlers():
        logging.basicConfig(level=logging.DEBUG) # Einfache Konfiguration falls kein Handler da ist

class BackendStatusMessage(BaseModel):
    """
    Represents a message indicating the backend's status.
    """
    type: Literal["status"] = "status"
    status: str  # e.g., "online", "maintenance", "startup", "shutdown"

class PingMessage(BaseModel):
    """
    Ping message sent from client to server for connection health check.
    """
    type: Literal["ping"] = "ping"
    timestamp: Optional[int] = None

class PongMessage(BaseModel):
    """
    Pong response message sent from server to client.
    """
    type: Literal["pong"] = "pong"
    timestamp: Optional[int] = None

class ConnectionStatusRequestMessage(BaseModel):
    """
    Request for connection status information.
    """
    type: Literal["connection_status_request"] = "connection_status_request"

class ConnectionStatusResponseMessage(BaseModel):
    """
    Response with connection status information.
    """
    type: Literal["connection_status_response"] = "connection_status_response"
    tenant_id: str
    backend_status: str
    connection_healthy: bool
    stats: Dict[str, Any]

# Enum definitions based on frontend types
class EntityType(Enum):
    ACCOUNT = "Account"
    ACCOUNT_GROUP = "AccountGroup"
    CATEGORY = "Category"
    CATEGORY_GROUP = "CategoryGroup"
    RECIPIENT = "Recipient"
    TAG = "Tag"
    AUTOMATION_RULE = "AutomationRule"
    PLANNING_TRANSACTION = "PlanningTransaction"
    TRANSACTION = "Transaction"
    TENANT = "Tenant"
    TENANT_DATABASE = "TenantDatabase"

class SyncOperationType(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    INITIAL_LOAD = "initial_load" # Hinzugefügt für den initialen Ladevorgang
    RESET = "reset" # Hinzugefügt für Tenant-Database-Reset

class AccountType(str, Enum):
    GIROKONTO = 'giro'
    TAGESGELDKONTO = 'tagesgeld'
    FESTGELDKONTO = 'festgeld'
    SPARKONTO = 'spar'
    KREDITKARTE = 'kreditkarte'
    DEPOT = 'depot'
    BAUSPARVERTRAG = 'bauspar'
    DARLEHENSKONTO = 'darlehen'
    GESCHAEFTSKONTO = 'geschaeft'
    GEMEINSCHAFTSKONTO = 'gemeinschaft'
    FREMDWAEHRUNGSKONTO = 'fremdwaehrung'
    VIRTUELL = 'virtuell'
    BARGELD = 'bar'
    CHECKING = 'checking'
    SONSTIGES = 'sonstiges'

# Pydantic models for payload data
class AccountPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    description: Optional[str] = None
    note: Optional[str] = None
    accountType: Optional[AccountType] = AccountType.SONSTIGES
    isActive: bool
    isOfflineBudget: bool
    accountGroupId: str # UUID as string from frontend
    sortOrder: Optional[int] = 0
    iban: Optional[str] = None
    balance: float # Assuming balance can be float
    creditLimit: Optional[float] = None # Assuming creditLimit can be float
    offset: int # Assuming offset is an integer
    logo_path: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None

    @validator('accountType', pre=True, always=True)
    def ensure_account_type_is_enum(cls, v):
        if isinstance(v, AccountType):
            logger.debug(f"Validator ensure_account_type_is_enum returning existing enum: {type(v)} - {v}")
            return v
        if isinstance(v, str):
            # Case-insensitive matching
            for member in AccountType:
                if member.value.lower() == v.lower():
                    logger.debug(f"Validator ensure_account_type_is_enum returning new enum from string: {type(member)} - {member}")
                    return member # Gibt das Enum-Mitglied zurück
            # If no match, raise error
            expected_values = [e.value for e in AccountType]
            raise ValueError(f"Ungültiger Wert '{v}' für AccountType. Erwartet einen von (case-insensitive): {expected_values}")
        if v is None:
            return AccountType.SONSTIGES  # Default value
        raise TypeError(f"Ungültiger Typ für AccountType: {type(v)}. Erwartet str oder AccountType.")

    class Config:
        use_enum_values = True # Enums als ihre Werte serialisieren
        from_attributes = True

class AccountGroupPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    sortOrder: int
    logo_path: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True # Enum-Objekte intern verwenden -> Geändert für Konsistenz und Zukunftssicherheit
        from_attributes = True

class CategoryPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    icon: Optional[str] = None
    budgeted: float
    activity: float
    available: float
    isIncomeCategory: bool
    isHidden: bool
    isActive: bool
    sortOrder: int
    categoryGroupId: Optional[str] = None
    parentCategoryId: Optional[str] = None
    isSavingsGoal: bool = False
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True

class CategoryGroupPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    sortOrder: int
    isIncomeGroup: bool
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True

class RecipientPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    defaultCategoryId: Optional[str] = None
    note: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True

class TagPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    parentTagId: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True

class AutomationRulePayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    description: Optional[str] = None
    stage: str # 'PRE' | 'DEFAULT' | 'POST'
    conditions: list[Dict[str, Any]] = Field(default_factory=list) # Array of RuleCondition objects
    actions: list[Dict[str, Any]] = Field(default_factory=list) # Array of RuleAction objects
    priority: int
    isActive: bool
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True

class PlanningTransactionPayload(BaseModel):
    id: str # UUID as string from frontend
    name: str
    accountId: str
    categoryId: Optional[str] = None
    tagIds: list[str] = Field(default_factory=list) # Array of tag IDs
    recipientId: Optional[str] = None
    amount: float
    amountType: str # 'EXACT', 'APPROXIMATE', 'RANGE'
    approximateAmount: Optional[float] = None
    minAmount: Optional[float] = None
    maxAmount: Optional[float] = None
    note: Optional[str] = None
    startDate: str # ISO 8601 date string
    valueDate: Optional[str] = None # ISO 8601 date string
    endDate: Optional[str] = None # ISO 8601 date string
    recurrencePattern: str # 'ONCE', 'DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY'
    recurrenceCount: Optional[int] = None
    recurrenceEndType: str # 'NEVER', 'COUNT', 'DATE'
    executionDay: Optional[int] = None
    weekendHandling: str # 'NONE', 'BEFORE', 'AFTER'
    transactionType: Optional[str] = None # 'EXPENSE', 'INCOME', 'ACCOUNTTRANSFER', 'CATEGORYTRANSFER', 'RECONCILE'
    counterPlanningTransactionId: Optional[str] = None
    transferToAccountId: Optional[str] = None
    transferToCategoryId: Optional[str] = None
    isActive: bool
    forecastOnly: bool
    autoExecute: Optional[bool] = False
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True

class TransactionPayload(BaseModel):
    id: str # UUID as string from frontend
    accountId: str
    categoryId: Optional[str] = None
    date: str # ISO 8601 date string
    valueDate: str # ISO 8601 date string
    amount: float
    description: Optional[str] = None  # Made optional to match frontend behavior
    note: Optional[str] = None
    tagIds: list[str] = Field(default_factory=list) # Array of tag IDs
    type: str # TransactionType enum: 'EXPENSE', 'INCOME', 'ACCOUNTTRANSFER', 'CATEGORYTRANSFER', 'RECONCILE'
    runningBalance: float
    counterTransactionId: Optional[str] = None
    planningTransactionId: Optional[str] = None
    isReconciliation: Optional[bool] = False
    isCategoryTransfer: Optional[bool] = False
    transferToAccountId: Optional[str] = None
    reconciled: Optional[bool] = False
    toCategoryId: Optional[str] = None
    payee: Optional[str] = None
    recipientId: Optional[str] = None  # Added missing field from frontend
    updated_at: Optional[datetime.datetime] = None

    class Config:
        use_enum_values = True
        from_attributes = True

# For DELETE operation, payload might just contain the ID or be null
class DeletePayload(BaseModel):
    id: str

# Union type for the payload based on entityType and operationType
SyncEntryDataPayload = Union[AccountPayload, AccountGroupPayload, CategoryPayload, CategoryGroupPayload, RecipientPayload, TagPayload, AutomationRulePayload, PlanningTransactionPayload, TransactionPayload, DeletePayload, None]

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
        if isinstance(v, EntityType):
            logger.debug(f"Validator ensure_entity_type_is_enum returning existing enum: {type(v)} - {v}")
            return v
        if isinstance(v, str):
            # Case-insensitive matching
            for member in EntityType:
                if member.value.lower() == v.lower():
                    logger.debug(f"Validator ensure_entity_type_is_enum returning new enum from string: {type(member)} - {member}")
                    return member # Gibt das Enum-Mitglied zurück
            # If no match, raise error
            expected_values = [e.value for e in EntityType]
            raise ValueError(f"Ungültiger Wert '{v}' für EntityType. Erwartet einen von (case-insensitive): {expected_values}")
        raise TypeError(f"Ungültiger Typ für EntityType: {type(v)}. Erwartet str oder EntityType.")

    @validator('operationType', pre=True, always=True)
    def ensure_operation_type_is_enum(cls, v):
        if isinstance(v, SyncOperationType):
            logger.debug(f"Validator ensure_operation_type_is_enum returning existing enum: {type(v)} - {v}")
            return v
        if isinstance(v, str):
            # Case-insensitive matching
            for member in SyncOperationType:
                if member.value.lower() == v.lower():
                    logger.debug(f"Validator ensure_operation_type_is_enum returning new enum from string: {type(member)} - {member}")
                    return member # Gibt das Enum-Mitglied zurück
            # If no match, raise error
            expected_values = [e.value for e in SyncOperationType]
            raise ValueError(f"Ungültiger Wert '{v}' für SyncOperationType. Erwartet einen von (case-insensitive): {expected_values}")
        raise TypeError(f"Ungültiger Typ für SyncOperationType: {type(v)}. Erwartet str oder SyncOperationType.")

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
            elif entity_type == EntityType.CATEGORY:
                if not isinstance(v, CategoryPayload):
                    if isinstance(v, dict):
                        return CategoryPayload(**v)
                    raise ValueError("Payload must be CategoryPayload for Category entity type")
            elif entity_type == EntityType.CATEGORY_GROUP:
                if not isinstance(v, CategoryGroupPayload):
                    if isinstance(v, dict):
                        return CategoryGroupPayload(**v)
                    raise ValueError("Payload must be CategoryGroupPayload for CategoryGroup entity type")
            elif entity_type == EntityType.RECIPIENT:
                if not isinstance(v, RecipientPayload):
                    if isinstance(v, dict):
                        return RecipientPayload(**v)
                    raise ValueError("Payload must be RecipientPayload for Recipient entity type")
            elif entity_type == EntityType.TAG:
                if not isinstance(v, TagPayload):
                    if isinstance(v, dict):
                        return TagPayload(**v)
                    raise ValueError("Payload must be TagPayload for Tag entity type")
            elif entity_type == EntityType.AUTOMATION_RULE:
                if not isinstance(v, AutomationRulePayload):
                    if isinstance(v, dict):
                        return AutomationRulePayload(**v)
                    raise ValueError("Payload must be AutomationRulePayload for AutomationRule entity type")
            elif entity_type == EntityType.PLANNING_TRANSACTION:
                if not isinstance(v, PlanningTransactionPayload):
                    if isinstance(v, dict):
                        return PlanningTransactionPayload(**v)
                    raise ValueError("Payload must be PlanningTransactionPayload for PlanningTransaction entity type")
            elif entity_type == EntityType.TRANSACTION:
                if not isinstance(v, TransactionPayload):
                    if isinstance(v, dict):
                        return TransactionPayload(**v)
                    raise ValueError("Payload must be TransactionPayload for Transaction entity type")
        return v

    class Config:
        use_enum_values = False # Sicherstellen, dass Enum-Objekte intern verwendet werden
        extra = 'ignore' # Ignore fields like 'status' from frontend if sent

class ProcessSyncEntryMessage(BaseModel):
    type: Literal["process_sync_entry"] = "process_sync_entry"
    payload: SyncQueueEntry

class RequestInitialDataMessage(BaseModel):
    """
    Message sent from frontend to backend to request initial data for the tenant.
    """
    type: Literal["request_initial_data"] = "request_initial_data"
    tenant_id: str # Zur Bestätigung, obwohl schon im WebSocket-Pfad

# Neue Schema-Definitionen für data_status_request und data_status_response
class DataStatusRequestMessage(BaseModel):
    """
    Message sent from frontend to backend to request data status for checksum comparison.
    """
    type: Literal["data_status_request"] = "data_status_request"
    tenant_id: str
    entity_types: Optional[list[EntityType]] = None  # Wenn None, alle Entitätstypen

class EntityChecksum(BaseModel):
    """
    Checksum information for a specific entity.
    """
    entity_id: str
    checksum: str
    last_modified: int  # Unix timestamp

class DataStatusResponseMessage(BaseModel):
    """
    Message sent from backend to frontend with data status and checksums.
    """
    type: Literal["data_status_response"] = "data_status_response"
    tenant_id: str
    entity_checksums: Dict[str, list[EntityChecksum]]  # Key: EntityType.value, Value: List of checksums
    last_sync_time: int
    server_time: int

# Schemas for Server-to-Client WebSocket messages

class ServerEventType(Enum):
    """
    Defines the type of event being sent from the server to the client.
    """
    DATA_UPDATE = "data_update"
    INITIAL_DATA_LOAD = "initial_data_load" # Hinzugefügt für den initialen Ladevorgang
    # Future event types can be added here, e.g., ERROR_NOTIFICATION, GENERAL_MESSAGE


# The 'data' field for a DATA_UPDATE notification message.
# It can be a full Account, AccountGroup, Category, CategoryGroup, Recipient, Tag, AutomationRule, PlanningTransaction, or Transaction payload for create/update operations,
# or a DeletePayload (containing just the ID) for delete operations.
NotificationDataPayload = Union[AccountPayload, AccountGroupPayload, CategoryPayload, CategoryGroupPayload, RecipientPayload, TagPayload, AutomationRulePayload, PlanningTransactionPayload, TransactionPayload, DeletePayload]


class DataUpdateNotificationMessage(BaseModel):
    """
    Pydantic model for WebSocket messages sent from the server to clients
    when data (Account, AccountGroup) is created, updated, or deleted.
    """
    event_type: ServerEventType = ServerEventType.DATA_UPDATE # Geändert von Literal
    tenant_id: str  # UUID of the tenant as a string
    entity_type: EntityType
    operation_type: SyncOperationType
    data: NotificationDataPayload

    class Config:
        use_enum_values = True  # Enums als ihre Werte serialisieren
        from_attributes = True

    @validator('data', pre=True, always=True)
    def validate_data_based_on_operation_and_entity(cls, v, values):
        """
        Validates that the 'data' payload matches the 'operation_type' and 'entity_type'.
        - For DELETE: 'data' must be DeletePayload.
        - For CREATE/UPDATE of Account: 'data' must be AccountPayload.
        - For CREATE/UPDATE of AccountGroup: 'data' must be AccountGroupPayload.
        """
        op_type_raw = values.get('operation_type') # This will be a string due to use_enum_values=True
        entity_type_raw = values.get('entity_type') # This will be a string due to use_enum_values=True

        # Convert op_type_raw string to SyncOperationType enum member for reliable comparison
        op_type: Optional[SyncOperationType] = None
        if isinstance(op_type_raw, str):
            try:
                op_type = SyncOperationType(op_type_raw)
            except ValueError:
                raise ValueError(f"Invalid operation_type string: {op_type_raw}")
        elif isinstance(op_type_raw, SyncOperationType): # Should not happen with use_enum_values=True but good for robustness
            op_type = op_type_raw
        else:
            raise ValueError(f"Unexpected type for operation_type: {type(op_type_raw)}")

        # Convert entity_type_raw string to EntityType enum member for reliable comparison
        entity_type: Optional[EntityType] = None
        if isinstance(entity_type_raw, str):
            try:
                entity_type = EntityType(entity_type_raw)
            except ValueError:
                # Log or handle the error if entity_type_raw is not a valid EntityType string
                raise ValueError(f"Invalid entity_type string: {entity_type_raw}. Expected one of {[e.value for e in EntityType]}")
        elif isinstance(entity_type_raw, EntityType): # Should not happen with use_enum_values=True but good for robustness
            entity_type = entity_type_raw
        else:
            raise ValueError(f"Unexpected type for entity_type: {type(entity_type_raw)}. Expected str or EntityType.")

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
        elif op_type == SyncOperationType.CREATE or op_type == SyncOperationType.UPDATE: # Explicit comparison
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
            elif entity_type == EntityType.CATEGORY:
                if not isinstance(v, CategoryPayload):
                    if isinstance(v, dict):
                        return CategoryPayload(**v)
                    raise ValueError(
                        f"For Category entity with {op_type.value} operation, 'data' must be CategoryPayload. Got: {type(v)}"
                    )
            elif entity_type == EntityType.CATEGORY_GROUP:
                if not isinstance(v, CategoryGroupPayload):
                    if isinstance(v, dict):
                        return CategoryGroupPayload(**v)
                    raise ValueError(
                        f"For CategoryGroup entity with {op_type.value} operation, 'data' must be CategoryGroupPayload. Got: {type(v)}"
                    )
            elif entity_type == EntityType.RECIPIENT:
                if not isinstance(v, RecipientPayload):
                    if isinstance(v, dict):
                        return RecipientPayload(**v)
                    raise ValueError(
                        f"For Recipient entity with {op_type.value} operation, 'data' must be RecipientPayload. Got: {type(v)}"
                    )
            elif entity_type == EntityType.TAG:
                if not isinstance(v, TagPayload):
                    if isinstance(v, dict):
                        return TagPayload(**v)
                    raise ValueError(
                        f"For Tag entity with {op_type.value} operation, 'data' must be TagPayload. Got: {type(v)}"
                    )
            elif entity_type == EntityType.AUTOMATION_RULE:
                if not isinstance(v, AutomationRulePayload):
                    if isinstance(v, dict):
                        return AutomationRulePayload(**v)
                    raise ValueError(
                        f"For AutomationRule entity with {op_type.value} operation, 'data' must be AutomationRulePayload. Got: {type(v)}"
                    )
            elif entity_type == EntityType.PLANNING_TRANSACTION:
                if not isinstance(v, PlanningTransactionPayload):
                    if isinstance(v, dict):
                        return PlanningTransactionPayload(**v)
                    raise ValueError(
                        f"For PlanningTransaction entity with {op_type.value} operation, 'data' must be PlanningTransactionPayload. Got: {type(v)}"
                    )
            elif entity_type == EntityType.TRANSACTION:
                if not isinstance(v, TransactionPayload):
                    if isinstance(v, dict):
                        return TransactionPayload(**v)
                    raise ValueError(
                        f"For Transaction entity with {op_type.value} operation, 'data' must be TransactionPayload. Got: {type(v)}"
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

class SyncAckMessage(BaseModel):
    """Message sent from server to client to acknowledge successful processing of a sync entry."""
    type: Literal["sync_ack"] = "sync_ack"
    id: str  # Corresponds to the SyncQueueEntry.id that was processed
    status: Literal["processed"] = "processed"
    entityId: str # UUID of the entity that was synced
    entityType: EntityType
    operationType: SyncOperationType

    class Config:
        use_enum_values = True # Ensure enums are serialized as their values

class SyncNackMessage(BaseModel):
    """Message sent from server to client to signal failure in processing a sync entry."""
    type: Literal["sync_nack"] = "sync_nack"
    id: str  # Corresponds to the SyncQueueEntry.id that failed
    status: Literal["failed"] = "failed"
    entityId: str # UUID of the entity that failed to sync
    entityType: EntityType
    operationType: SyncOperationType
    reason: str  # A brief reason for the failure, e.g., "database_error", "validation_error", "table_not_found"
    detail: Optional[str] = None # More detailed error message if available

    class Config:
        use_enum_values = True # Ensure enums are serialized as their values

# Optional: A Union of all possible messages the server might send to the client.
# This can be useful for type hinting in the ConnectionManager or endpoint.

# Payload for the initial data load message
class InitialDataPayload(BaseModel):
    accounts: list[AccountPayload] = Field(default_factory=list)
    account_groups: list[AccountGroupPayload] = Field(default_factory=list)
    categories: list[CategoryPayload] = Field(default_factory=list)
    category_groups: list[CategoryGroupPayload] = Field(default_factory=list)
    recipients: list[RecipientPayload] = Field(default_factory=list)
    tags: list[TagPayload] = Field(default_factory=list)
    automation_rules: list[AutomationRulePayload] = Field(default_factory=list)
    planning_transactions: list[PlanningTransactionPayload] = Field(default_factory=list)
    transactions: list[TransactionPayload] = Field(default_factory=list)

class InitialDataLoadMessage(BaseModel):
    """
    Message sent from server to client containing the initial set of data for a tenant.
    """
    event_type: ServerEventType = ServerEventType.INITIAL_DATA_LOAD # Geändert von Literal
    tenant_id: str
    payload: InitialDataPayload

    class Config:
        use_enum_values = True

# Erweiterte Schemas für Sync-Management
class SyncConflictEntry(BaseModel):
    """
    Represents a conflict between local and server data.
    """
    entity_type: EntityType
    entity_id: str
    local_checksum: str
    server_checksum: str
    local_last_modified: int
    server_last_modified: int

class ConflictReportMessage(BaseModel):
    """
    Message sent from server to client with conflict information.
    """
    type: Literal["conflict_report"] = "conflict_report"
    tenant_id: str
    conflicts: list[SyncConflictEntry]
    local_only: list[Dict[str, str]]  # entities that exist only locally
    server_only: list[Dict[str, str]]  # entities that exist only on server

class SyncStatusMessage(BaseModel):
    """
    Message sent from server to client with sync status information.
    """
    type: Literal["sync_status"] = "sync_status"
    tenant_id: str
    queue_length: int
    last_sync_time: int
    sync_in_progress: bool
    failed_entries_count: int

ServerToClientMessage = Union[
    DataUpdateNotificationMessage,
    BackendStatusMessage,
    SyncAckMessage,
    SyncNackMessage,
    InitialDataLoadMessage,
    DataStatusResponseMessage,
    ConflictReportMessage,
    SyncStatusMessage,
    PongMessage,
    ConnectionStatusResponseMessage
]

ClientToServerMessage = Union[
    ProcessSyncEntryMessage,
    RequestInitialDataMessage,
    DataStatusRequestMessage,
    PingMessage,
    ConnectionStatusRequestMessage
]
# For now, we'll handle DataUpdateNotificationMessage and InitialDataLoadMessage specifically.
