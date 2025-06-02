from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
import json # Import json for potential string conversion if needed, though Pydantic handles it

from app.api import deps
from app.websocket.connection_manager import manager
from app.models.user_tenant_models import User
from app.websocket.schemas import BackendStatusMessage # Import Pydantic model

router = APIRouter()

@router.websocket("/ws/{tenant_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    # current_user: User = Depends(deps.get_current_active_user), # Vorerst auskommentiert
    # db: Session = Depends(deps.get_db) # Vorerst auskommentiert
):
    await manager.connect(websocket, tenant_id)
    try:
        # Send initial online status message using the Pydantic model
        online_status_message = BackendStatusMessage(status="online")
        await manager.send_personal_json_message(online_status_message.model_dump(), websocket)

        while True:
            data = await websocket.receive_text()
            # Process received message (currently just echoing)
            # For now, we'll keep the echo simple.
            # In a real scenario, you'd parse 'data' and react accordingly.
            await manager.send_personal_message(f"Nachricht empfangen: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)
        # Optional: Notify other clients in the same tenant about the disconnect
        # await manager.broadcast_to_tenant(f"Ein Client von Tenant {tenant_id} hat die Verbindung getrennt.", tenant_id)
    except Exception as e:
        print(f"Error in websocket connection for tenant {tenant_id}: {e}")
        # Ensure disconnect on any other error
        manager.disconnect(websocket, tenant_id)


# Function to allow other parts of the backend to broadcast a status change
async def broadcast_backend_status(status: str):
    """
    Broadcasts the backend status (e.g., "online", "maintenance") to all connected clients.
    This function can be called from other parts of the backend to signal a global status change.
    """
    # Uses the new method in ConnectionManager which handles Pydantic model creation
    await manager.broadcast_backend_status_message(status)


# Zukünftige Erweiterung für Datenänderungsbenachrichtigungen
# This function remains for future use, potentially using Pydantic models as well.
async def notify_data_change(tenant_id: str, entity_type: str, entity_id: str, action: str, data: dict):
    """
    Sendet eine Benachrichtigung über Datenänderungen an alle Clients eines Tenants.
    Beispiel: notify_data_change("tenant_xyz", "account", "acc_123", "updated", {"balance": 1500})
    """
    # TODO: Consider creating a Pydantic model for this message type as well
    message = {
        "type": "data_update",
        "entity": entity_type,
        "id": entity_id,
        "action": action, # "created", "updated", "deleted"
        "payload": data
    }
    # For now, sending as a string. Could be upgraded to send_json with a Pydantic model.
    await manager.broadcast_to_tenant(json.dumps(message), tenant_id)

# The old broadcast_backend_status function (lines 54-62) is now effectively replaced
# by the new broadcast_backend_status function (lines 39-45 in this diff)
# and the logic moved into ConnectionManager.broadcast_backend_status_message.
# We remove the old one to avoid confusion.
