from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
import json
from pydantic import ValidationError

from app.api import deps
from app.websocket.connection_manager import manager
# from app.models.user_tenant_models import User # Not directly used in this endpoint for now
from app.websocket.schemas import BackendStatusMessage, ProcessSyncEntryMessage # Import new schema
from app.services import sync_service # Import the new sync service
from app.utils.logger import debugLog, errorLog, infoLog # Added infoLog

router = APIRouter()

@router.websocket("/ws/{tenant_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    # current_user: User = Depends(deps.get_current_active_user), # Vorerst auskommentiert
    # db: Session = Depends(deps.get_db) # Vorerst auskommentiert
):
    await manager.connect(websocket, tenant_id)
    debugLog(
        "WebSocketEndpoints",
        f"WebSocket connected for tenant: {tenant_id}",
        details={"tenant_id": tenant_id, "client_host": websocket.client.host if websocket.client else "Unknown"}
    )
    try:
        # Send initial online status message using the Pydantic model
        online_status_message = BackendStatusMessage(status="online")
        await manager.send_personal_json_message(online_status_message.model_dump(), websocket)
        debugLog(
            "WebSocketEndpoints",
            "Sent initial 'online' status to client.",
            details={"tenant_id": tenant_id, "client_host": websocket.client.host if websocket.client else "Unknown", "status": "online"}
        )

        while True:
            data = await websocket.receive_text()
            debugLog(
                "WebSocketEndpoints",
                f"Received text data from client for tenant {tenant_id}",
                details={"tenant_id": tenant_id, "client_host": websocket.client.host if websocket.client else "Unknown", "data_length": len(data), "data_preview": data[:100]}
            )

            try:
                message_data = json.loads(data)
                message_type = message_data.get("type")

                if message_type == "process_sync_entry":
                    try:
                        # Log incoming payload types before Pydantic validation
                        payload_data = message_data.get("payload", {})
                        entity_type_raw = payload_data.get("entityType")
                        operation_type_raw = payload_data.get("operationType")
                        debugLog(
                            "WebSocketEndpoints",
                            f"Pre-validation: entityType raw: {entity_type_raw} (type: {type(entity_type_raw)}), operationType raw: {operation_type_raw} (type: {type(operation_type_raw)})",
                            details={"tenant_id": tenant_id, "raw_message_data": message_data}
                        )

                        sync_entry_message = ProcessSyncEntryMessage(**message_data)

                        # Log types after Pydantic validation
                        debugLog(
                            "WebSocketEndpoints",
                            f"Post-validation: entityType: {sync_entry_message.payload.entityType} (type: {type(sync_entry_message.payload.entityType)}), operationType: {sync_entry_message.payload.operationType} (type: {type(sync_entry_message.payload.operationType)})",
                            details={"tenant_id": tenant_id, "payload_id": sync_entry_message.payload.id}
                        )

                        infoLog(
                            "WebSocketEndpoints",
                            f"Received process_sync_entry for tenant {tenant_id}, entity {sync_entry_message.payload.entityType.value} {sync_entry_message.payload.entityId}",
                            details={"tenant_id": tenant_id, "entry_id": sync_entry_message.payload.id}
                        )
                        # Process the sync entry using the service
                        # This is a synchronous call within an async function.
                        # For long-running tasks, consider background tasks.
                        success = sync_service.process_sync_entry(sync_entry_message.payload, source_websocket=websocket)

                        if success:
                            infoLog(
                                "WebSocketEndpoints",
                                f"Successfully processed sync entry {sync_entry_message.payload.id} for tenant {tenant_id}",
                                details={"tenant_id": tenant_id, "entry_id": sync_entry_message.payload.id}
                            )
                            # TODO: Send confirmation back to client (Step 8)
                            # await manager.send_personal_json_message({"type": "sync_ack", "id": sync_entry_message.payload.id, "status": "processed"}, websocket)
                        else:
                            errorLog(
                                "WebSocketEndpoints",
                                f"Failed to process sync entry {sync_entry_message.payload.id} for tenant {tenant_id}",
                                details={"tenant_id": tenant_id, "entry_id": sync_entry_message.payload.id}
                            )
                            # TODO: Send error back to client (Step 8)
                            # await manager.send_personal_json_message({"type": "sync_nack", "id": sync_entry_message.payload.id, "status": "failed", "reason": "processing_error"}, websocket)

                    except ValidationError as ve:
                        errorLog(
                            "WebSocketEndpoints",
                            f"Validation error for process_sync_entry message from tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "error": ve.errors(), "data": data[:200]}
                        )
                        # Optionally send a specific error message back to the client
                        # await manager.send_personal_json_message({"type": "error", "message": "Invalid sync entry format", "details": ve.errors()}, websocket)
                    except Exception as proc_e: # Catch errors during processing
                        errorLog(
                            "WebSocketEndpoints",
                            f"Error processing sync_entry message for tenant {tenant_id}: {str(proc_e)}",
                            details={"tenant_id": tenant_id, "error": str(proc_e), "data": data[:200]}
                        )
                        # TODO: Send error back to client (Step 8)

                elif message_type: # Handle other known message types if any
                    debugLog(
                        "WebSocketEndpoints",
                        f"Received unhandled message type '{message_type}' from tenant {tenant_id}",
                        details={"tenant_id": tenant_id, "data": data[:200]}
                    )
                    # Echo back for unknown types for now, or handle them
                    await manager.send_personal_message(f"Unbekannter Nachrichtentyp empfangen: {message_type}", websocket)
                else: # No type field or unknown structure
                    debugLog(
                        "WebSocketEndpoints",
                        f"Received message without 'type' field or unknown structure from tenant {tenant_id}",
                        details={"tenant_id": tenant_id, "data": data[:200]}
                    )
                    await manager.send_personal_message(f"Nachricht ohne Typfeld empfangen: {data[:50]}...", websocket)

            except json.JSONDecodeError:
                errorLog(
                    "WebSocketEndpoints",
                    f"Received invalid JSON from client for tenant {tenant_id}",
                    details={"tenant_id": tenant_id, "data": data[:200]} # Log only a preview
                )
                await manager.send_personal_message("Fehler: Ungültiges JSON-Format.", websocket)
            except Exception as e_outer: # Catch any other unexpected errors in the loop
                 errorLog(
                    "WebSocketEndpoints",
                    f"Outer loop exception for tenant {tenant_id}: {str(e_outer)}",
                    details={"tenant_id": tenant_id, "error": str(e_outer), "data": data[:200]}
                )
                # Consider if we should break or continue based on the error.
                # For now, we log and continue, but a critical error might warrant a disconnect.

    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)
        debugLog(
            "WebSocketEndpoints",
            f"WebSocket disconnected for tenant: {tenant_id}",
            details={"tenant_id": tenant_id, "client_host": websocket.client.host if websocket.client else "Unknown", "reason": "WebSocketDisconnect"}
        )
        # Optional: Notify other clients in the same tenant about the disconnect
        # await manager.broadcast_to_tenant(f"Ein Client von Tenant {tenant_id} hat die Verbindung getrennt.", tenant_id)
    except Exception as e:
        errorLog( # Using errorLog as per import
            "WebSocketEndpoints",
            f"Error in websocket connection for tenant {tenant_id}",
            details={"tenant_id": tenant_id, "client_host": websocket.client.host if websocket.client else "Unknown", "error": str(e), "error_type": type(e).__name__}
        )
        # Ensure disconnect on any other error
        manager.disconnect(websocket, tenant_id)
        debugLog( # Add debug log for disconnect after error
            "WebSocketEndpoints",
            f"WebSocket disconnected due to error for tenant: {tenant_id}",
            details={"tenant_id": tenant_id, "client_host": websocket.client.host if websocket.client else "Unknown", "reason": "Exception"}
        )


# Function to allow other parts of the backend to broadcast a status change
async def broadcast_backend_status(status: str):
    """
    Broadcasts the backend status (e.g., "online", "maintenance") to all connected clients.
    This function can be called from other parts of the backend to signal a global status change.
    """
    debugLog(
        "WebSocketEndpoints",
        f"Attempting to broadcast backend status: {status}",
        details={"status": status}
    )
    # Uses the new method in ConnectionManager which handles Pydantic model creation
    await manager.broadcast_backend_status_message(status)
    debugLog( # Log after successful broadcast attempt
        "WebSocketEndpoints",
        f"Successfully initiated broadcast of backend status: {status}",
        details={"status": status}
    )


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
    debugLog(
        "WebSocketEndpoints",
        f"Notified data change for tenant {tenant_id}",
        details={
            "tenant_id": tenant_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "data_keys": list(data.keys()) if isinstance(data, dict) else None
        }
    )

# The old broadcast_backend_status function (lines 54-62) is now effectively replaced
# by the new broadcast_backend_status function (lines 39-45 in this diff)
# and the logic moved into ConnectionManager.broadcast_backend_status_message.
# We remove the old one to avoid confusion.
