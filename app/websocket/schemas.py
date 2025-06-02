from pydantic import BaseModel
from typing import Literal

class BackendStatusMessage(BaseModel):
    """
    Represents a message indicating the backend's status.
    """
    type: Literal["status"] = "status"
    status: str  # e.g., "online", "maintenance"

# Future Pydantic models for other WebSocket messages can be added here.
# For example, for data updates:
#
# class DataUpdatePayload(BaseModel):
#     entity: str
#     id: str
#     action: Literal["created", "updated", "deleted"]
#     data: dict
#
# class DataUpdateMessage(BaseModel):
#     type: Literal["data_update"] = "data_update"
#     payload: DataUpdatePayload
