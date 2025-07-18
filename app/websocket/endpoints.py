from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
import json
import asyncio
from pydantic import ValidationError
from fastapi.encoders import jsonable_encoder

from app.api import deps
from app.api.deps import set_current_tenant_id
from app.websocket.connection_manager import manager
# from app.models.user_tenant_models import User # Not directly used in this endpoint for now
from app.websocket.schemas import (
    BackendStatusMessage, ProcessSyncEntryMessage, SyncAckMessage, SyncNackMessage,
    RequestInitialDataMessage, InitialDataLoadMessage, ServerEventType, # Import new schemas for initial data load
    DataStatusRequestMessage, DataStatusResponseMessage, # Import new schemas for data status
    ProcessSyncQueueMessage, SyncQueueStatusMessage # Import new schemas for staged sync
)
from app.services import sync_service # Import the new sync service
from app.utils.logger import debugLog, errorLog, infoLog, warnLog # Added warnLog

router = APIRouter()

@router.websocket("/ws/{tenant_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    # current_user: User = Depends(deps.get_current_active_user), # Vorerst auskommentiert
    # db: Session = Depends(deps.get_db) # Vorerst auskommentiert
):
    # Set the tenant ID in the context for this WebSocket connection
    set_current_tenant_id(tenant_id)

    await manager.connect(websocket, tenant_id)
    debugLog(
        "WebSocketEndpoints",
        f"WebSocket connected for tenant: {tenant_id} (context set)",
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
            try:
                # Verwende receive() anstatt receive_text() um verschiedene Nachrichtentypen zu handhaben
                message = await websocket.receive()

                # Handle verschiedene WebSocket-Nachrichtentypen
                if message["type"] == "websocket.disconnect":
                    break
                elif message["type"] == "websocket.receive":
                    if "text" in message:
                        data = message["text"]
                    elif "bytes" in message:
                        # Für Ping/Pong-Nachrichten - diese werden automatisch von FastAPI gehandhabt
                        continue
                    else:
                        continue
                else:
                    continue
            except Exception as receive_error:
                errorLog(
                    "WebSocketEndpoints",
                    f"Fehler beim Empfangen von WebSocket-Nachricht für Tenant {tenant_id}",
                    details={"tenant_id": tenant_id, "error": str(receive_error)}
                )
                break
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
                        # The process_sync_entry now returns a tuple: (bool_success, str_reason_if_failed)
                        # First, add the entry to the sync queue for tracking
                        sync_service.add_to_sync_queue(tenant_id, sync_entry_message.payload)

                        success, reason_or_detail = await sync_service.process_sync_entry(sync_entry_message.payload, source_websocket=websocket)

                        if success:
                            # Remove from queue on success
                            sync_service.remove_from_sync_queue(tenant_id, sync_entry_message.payload.id)

                            infoLog(
                                "WebSocketEndpoints",
                                f"Successfully processed sync entry {sync_entry_message.payload.id} for tenant {tenant_id}",
                                details={"tenant_id": tenant_id, "entry_id": sync_entry_message.payload.id}
                            )
                            ack_message = SyncAckMessage(
                                id=sync_entry_message.payload.id,
                                entityId=sync_entry_message.payload.entityId,
                                entityType=sync_entry_message.payload.entityType,
                                operationType=sync_entry_message.payload.operationType
                            )
                            await manager.send_personal_json_message(ack_message.model_dump(), websocket)
                        else:
                            # Add to failed entries for retry logic
                            sync_service.add_failed_entry(tenant_id, sync_entry_message.payload.id, reason_or_detail or "processing_error")

                            errorLog(
                                "WebSocketEndpoints",
                                f"Failed to process sync entry {sync_entry_message.payload.id} for tenant {tenant_id}. Reason: {reason_or_detail}",
                                details={"tenant_id": tenant_id, "entry_id": sync_entry_message.payload.id, "reason": reason_or_detail}
                            )
                            nack_message = SyncNackMessage(
                                id=sync_entry_message.payload.id,
                                entityId=sync_entry_message.payload.entityId,
                                entityType=sync_entry_message.payload.entityType,
                                operationType=sync_entry_message.payload.operationType,
                                reason=reason_or_detail if reason_or_detail else "processing_error",
                                detail=f"Failed to process sync entry {sync_entry_message.payload.id}" # Can be more specific if needed
                            )
                            await manager.send_personal_json_message(nack_message.model_dump(), websocket)

                    except ValidationError as ve:
                        error_detail_for_client = f"Validation error for sync entry: {str(ve)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Validation error for process_sync_entry message from tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "error": ve.errors(), "data": data[:200]}
                        )
                        # Send NACK for validation error
                        try: # Try to get entry details for NACK, might fail if initial parsing failed badly
                            sync_entry_message_for_nack = ProcessSyncEntryMessage(**message_data)
                            nack_validation_message = SyncNackMessage(
                                id=sync_entry_message_for_nack.payload.id if sync_entry_message_for_nack.payload else "unknown_entry_id",
                                entityId=sync_entry_message_for_nack.payload.entityId if sync_entry_message_for_nack.payload else "unknown_entity_id",
                                entityType=sync_entry_message_for_nack.payload.entityType if sync_entry_message_for_nack.payload else "Unknown", # Provide a default
                                operationType=sync_entry_message_for_nack.payload.operationType if sync_entry_message_for_nack.payload else "Unknown", # Provide a default
                                reason="validation_error",
                                detail=error_detail_for_client
                            )
                            await manager.send_personal_json_message(nack_validation_message.model_dump(), websocket)
                        except Exception: # Fallback if payload parsing for NACK fails
                             await manager.send_personal_json_message({"type": "sync_nack", "id": message_data.get("payload", {}).get("id", "unknown"), "status": "failed", "reason": "validation_error", "detail": "Invalid message structure."}, websocket)

                    except Exception as proc_e: # Catch errors during processing
                        error_detail_for_client = f"Error processing sync entry: {str(proc_e)}"
                        # Use warnLog for expected processing issues, errorLog for unexpected crashes
                        if "websocket_state_error" in str(proc_e) or "db_locked" in str(proc_e):
                            warnLog(
                                "WebSocketEndpoints",
                                f"Recoverable error processing sync_entry for tenant {tenant_id}: {str(proc_e)}",
                                details={"tenant_id": tenant_id, "error": str(proc_e), "data": data[:200]}
                            )
                        else:
                            errorLog(
                                "WebSocketEndpoints",
                                f"Critical error processing sync_entry for tenant {tenant_id}: {str(proc_e)}",
                                details={"tenant_id": tenant_id, "error": str(proc_e), "data": data[:200]}
                            )
                        # Send NACK for general processing error
                        try: # Try to get entry details for NACK
                            sync_entry_message_for_nack = ProcessSyncEntryMessage(**message_data)
                            nack_processing_message = SyncNackMessage(
                                id=sync_entry_message_for_nack.payload.id if sync_entry_message_for_nack.payload else "unknown_entry_id",
                                entityId=sync_entry_message_for_nack.payload.entityId if sync_entry_message_for_nack.payload else "unknown_entity_id",
                                entityType=sync_entry_message_for_nack.payload.entityType if sync_entry_message_for_nack.payload else "Unknown",
                                operationType=sync_entry_message_for_nack.payload.operationType if sync_entry_message_for_nack.payload else "Unknown",
                                reason="processing_error",
                                detail=error_detail_for_client
                            )
                            await manager.send_personal_json_message(nack_processing_message.model_dump(), websocket)
                        except Exception: # Fallback if payload parsing for NACK fails
                            await manager.send_personal_json_message({"type": "sync_nack", "id": message_data.get("payload", {}).get("id", "unknown"), "status": "failed", "reason": "processing_error", "detail": "Internal server error during processing."}, websocket)


                elif message_type == "request_initial_data":
                    try:
                        request_initial_data_message = RequestInitialDataMessage(**message_data)
                        infoLog(
                            "WebSocketEndpoints",
                            f"Received request_initial_data for tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "client_host": websocket.client.host if websocket.client else "Unknown"}
                        )

                        initial_data_payload, error_msg = await sync_service.get_initial_data_for_tenant(tenant_id)

                        if initial_data_payload:
                            response_message = InitialDataLoadMessage(
                                tenant_id=tenant_id,
                                payload=initial_data_payload
                            )
                            await manager.send_personal_json_message(jsonable_encoder(response_message), websocket)
                            infoLog(
                                "WebSocketEndpoints",
                                f"Sent initial_data_load to client for tenant {tenant_id}. Accounts: {len(initial_data_payload.accounts)}, Groups: {len(initial_data_payload.account_groups)}",
                                details={"tenant_id": tenant_id}
                            )
                        else:
                            errorLog(
                                "WebSocketEndpoints",
                                f"Failed to get initial data for tenant {tenant_id}: {error_msg}",
                                details={"tenant_id": tenant_id, "error_message": error_msg}
                            )
                            # Optionally send an error message back to the client
                            await manager.send_personal_json_message(
                                {"type": "error", "message": f"Failed to load initial data: {error_msg}"},
                                websocket
                            )
                    except ValidationError as ve:
                        error_detail_for_client = f"Validation error for request_initial_data: {str(ve)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Validation error for request_initial_data message from tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "error": ve.errors(), "data": data[:200]}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)
                    except Exception as e_initial_data:
                        error_detail_for_client = f"Error processing request_initial_data: {str(e_initial_data)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Error processing request_initial_data for tenant {tenant_id}: {str(e_initial_data)}",
                            details={"tenant_id": tenant_id, "error": str(e_initial_data), "data": data[:200]}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)

                elif message_type == "data_status_request":
                    try:
                        data_status_request = DataStatusRequestMessage(**message_data)
                        infoLog(
                            "WebSocketEndpoints",
                            f"Received data_status_request for tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "entity_types": data_status_request.entity_types}
                        )

                        # Process data status request using the service
                        status_response = await sync_service.get_data_status_for_tenant(
                            data_status_request.tenant_id,
                            data_status_request.entity_types
                        )

                        if status_response:
                            await manager.send_personal_json_message(status_response.model_dump(), websocket)
                            infoLog(
                                "WebSocketEndpoints",
                                f"Sent data_status_response to client for tenant {tenant_id}",
                                details={"tenant_id": tenant_id, "entity_count": len(status_response.entity_checksums)}
                            )
                        else:
                            errorLog(
                                "WebSocketEndpoints",
                                f"Failed to get data status for tenant {tenant_id}",
                                details={"tenant_id": tenant_id}
                            )
                            await manager.send_personal_json_message(
                                {"type": "error", "message": "Failed to get data status"},
                                websocket
                            )
                    except ValidationError as ve:
                        error_detail_for_client = f"Validation error for data_status_request: {str(ve)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Validation error for data_status_request message from tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "error": ve.errors(), "data": data[:200]}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)
                    except Exception as e_data_status:
                        error_detail_for_client = f"Error processing data_status_request: {str(e_data_status)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Error processing data_status_request for tenant {tenant_id}: {str(e_data_status)}",
                            details={"tenant_id": tenant_id, "error": str(e_data_status), "data": data[:200]}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)

                elif message_type == "process_sync_queue":
                    try:
                        sync_queue_message = ProcessSyncQueueMessage(**message_data)
                        infoLog(
                            "WebSocketEndpoints",
                            f"Received process_sync_queue for tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "use_staged_sync": sync_queue_message.use_staged_sync}
                        )

                        # Process the sync queue using staged synchronization if requested
                        if sync_queue_message.use_staged_sync:
                            # Use the new staged sync processing
                            queue_result = await sync_service.process_sync_queue_for_tenant(tenant_id, source_websocket=websocket)
                        else:
                            # Use regular sync processing (fallback)
                            queue_result = await sync_service.process_sync_queue_for_tenant(tenant_id, source_websocket=websocket)

                        # Send response with queue processing results
                        response_message = SyncQueueStatusMessage(
                            tenant_id=tenant_id,
                            processed_count=queue_result.get("processed", 0),
                            successful_count=queue_result.get("successful", 0),
                            failed_count=queue_result.get("failed", 0),
                            failed_entries=queue_result.get("failed_entries", []),
                            has_pending_entries=queue_result.get("failed", 0) > 0
                        )

                        await manager.send_personal_json_message(response_message.model_dump(), websocket)
                        infoLog(
                            "WebSocketEndpoints",
                            f"Sent sync_queue_status to client for tenant {tenant_id}. Processed: {queue_result.get('processed', 0)}, Success: {queue_result.get('successful', 0)}, Failed: {queue_result.get('failed', 0)}",
                            details={"tenant_id": tenant_id, "queue_result": queue_result}
                        )

                    except ValidationError as ve:
                        error_detail_for_client = f"Validation error for process_sync_queue: {str(ve)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Validation error for process_sync_queue message from tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "error": ve.errors(), "data": data[:200]}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)
                    except Exception as e_sync_queue:
                        error_detail_for_client = f"Error processing sync queue: {str(e_sync_queue)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Error processing sync queue for tenant {tenant_id}: {str(e_sync_queue)}",
                            details={"tenant_id": tenant_id, "error": str(e_sync_queue), "data": data[:200]}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)

                elif message_type == "retry_failed_entries":
                    try:
                        infoLog(
                            "WebSocketEndpoints",
                            f"Received retry_failed_entries for tenant {tenant_id}",
                            details={"tenant_id": tenant_id}
                        )

                        # Retry failed entries for the tenant
                        retry_result = await sync_service.retry_failed_entries_for_tenant(tenant_id, source_websocket=websocket)

                        # Send response with retry results
                        response_message = SyncQueueStatusMessage(
                            tenant_id=tenant_id,
                            processed_count=retry_result.get("retried", 0),
                            successful_count=retry_result.get("successful", 0),
                            failed_count=retry_result.get("failed", 0),
                            failed_entries=retry_result.get("failed_entries", []),
                            has_pending_entries=retry_result.get("failed", 0) > 0
                        )

                        await manager.send_personal_json_message(response_message.model_dump(), websocket)
                        infoLog(
                            "WebSocketEndpoints",
                            f"Sent retry results to client for tenant {tenant_id}. Retried: {retry_result.get('retried', 0)}, Success: {retry_result.get('successful', 0)}, Failed: {retry_result.get('failed', 0)}",
                            details={"tenant_id": tenant_id, "retry_result": retry_result}
                        )

                    except Exception as e_retry:
                        error_detail_for_client = f"Error retrying failed entries: {str(e_retry)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Error retrying failed entries for tenant {tenant_id}: {str(e_retry)}",
                            details={"tenant_id": tenant_id, "error": str(e_retry)}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)

                elif message_type == "get_sync_queue_status":
                    try:
                        infoLog(
                            "WebSocketEndpoints",
                            f"Received get_sync_queue_status for tenant {tenant_id}",
                            details={"tenant_id": tenant_id}
                        )

                        # Get sync queue status for the tenant
                        queue_status = sync_service.get_sync_queue_status(tenant_id)

                        # Send response with queue status
                        response_message = {
                            "type": "sync_queue_status_info",
                            "tenant_id": tenant_id,
                            "pending_count": queue_status.get("pending_count", 0),
                            "failed_count": queue_status.get("failed_count", 0),
                            "retryable_count": queue_status.get("retryable_count", 0),
                            "has_pending_entries": queue_status.get("has_pending_entries", False)
                        }

                        await manager.send_personal_json_message(response_message, websocket)
                        debugLog(
                            "WebSocketEndpoints",
                            f"Sent sync queue status to client for tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "queue_status": queue_status}
                        )

                    except Exception as e_status:
                        error_detail_for_client = f"Error getting sync queue status: {str(e_status)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Error getting sync queue status for tenant {tenant_id}: {str(e_status)}",
                            details={"tenant_id": tenant_id, "error": str(e_status)}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)

                elif message_type == "trigger_cyclic_sync":
                    try:
                        infoLog(
                            "WebSocketEndpoints",
                            f"Received trigger_cyclic_sync for tenant {tenant_id}",
                            details={"tenant_id": tenant_id}
                        )

                        # Trigger cyclic sync if needed
                        sync_result = await sync_service.trigger_cyclic_sync_if_needed(tenant_id, source_websocket=websocket)

                        # Send response with sync results
                        response_message = {
                            "type": "cyclic_sync_result",
                            "tenant_id": tenant_id,
                            "triggered": sync_result.get("triggered", False),
                            "total_processed": sync_result.get("total_processed", 0),
                            "total_successful": sync_result.get("total_successful", 0),
                            "total_failed": sync_result.get("total_failed", 0),
                            "reason": sync_result.get("reason"),
                            "error": sync_result.get("error")
                        }

                        await manager.send_personal_json_message(response_message, websocket)
                        infoLog(
                            "WebSocketEndpoints",
                            f"Sent cyclic sync result to client for tenant {tenant_id}. Triggered: {sync_result.get('triggered', False)}, Processed: {sync_result.get('total_processed', 0)}",
                            details={"tenant_id": tenant_id, "sync_result": sync_result}
                        )

                    except Exception as e_cyclic:
                        error_detail_for_client = f"Error triggering cyclic sync: {str(e_cyclic)}"
                        errorLog(
                            "WebSocketEndpoints",
                            f"Error triggering cyclic sync for tenant {tenant_id}: {str(e_cyclic)}",
                            details={"tenant_id": tenant_id, "error": str(e_cyclic)}
                        )
                        await manager.send_personal_json_message({"type": "error", "message": error_detail_for_client}, websocket)

                elif message_type == "ping":
                    # Handle explizite Ping-Nachrichten vom Client
                    try:
                        debugLog(
                            "WebSocketEndpoints",
                            f"Received ping from tenant {tenant_id}",
                            details={"tenant_id": tenant_id}
                        )
                        await manager.send_personal_json_message({"type": "pong", "timestamp": message_data.get("timestamp")}, websocket)
                    except Exception as ping_error:
                        errorLog(
                            "WebSocketEndpoints",
                            f"Fehler beim Verarbeiten von Ping für Tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "error": str(ping_error)}
                        )

                elif message_type == "connection_status_request":
                    # Handle Verbindungsstatus-Anfragen
                    try:
                        connection_stats = await manager.get_connection_stats()
                        status_response = {
                            "type": "connection_status_response",
                            "tenant_id": tenant_id,
                            "backend_status": "online",
                            "connection_healthy": manager.connection_health.get(websocket, True),
                            "stats": connection_stats
                        }
                        await manager.send_personal_json_message(status_response, websocket)
                        debugLog(
                            "WebSocketEndpoints",
                            f"Sent connection status to tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "stats": connection_stats}
                        )
                    except Exception as status_error:
                        errorLog(
                            "WebSocketEndpoints",
                            f"Fehler beim Senden des Verbindungsstatus für Tenant {tenant_id}",
                            details={"tenant_id": tenant_id, "error": str(status_error)}
                        )

                elif message_type: # Handle other known message types if any
                    debugLog(
                        "WebSocketEndpoints",
                        f"Received unhandled message type '{message_type}' from tenant {tenant_id}",
                        details={"tenant_id": tenant_id, "data": data[:200]}
                    )
                    # Send JSON error message instead of plain text
                    await manager.send_personal_json_message({
                        "type": "error",
                        "message": f"Unbekannter Nachrichtentyp empfangen: {message_type}",
                        "original_type": message_type
                    }, websocket)
                else: # No type field or unknown structure
                    debugLog(
                        "WebSocketEndpoints",
                        f"Received message without 'type' field or unknown structure from tenant {tenant_id}",
                        details={"tenant_id": tenant_id, "data": data[:200]}
                    )
                    await manager.send_personal_json_message({
                        "type": "error",
                        "message": f"Nachricht ohne Typfeld empfangen: {data[:50]}...",
                        "original_data": data[:100]
                    }, websocket)

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

async def broadcast_backend_startup():
    """
    Sendet eine Startup-Nachricht an alle verbundenen Clients.
    Diese Funktion wird beim Backend-Start aufgerufen.
    """
    infoLog(
        "WebSocketEndpoints",
        "Broadcasting backend startup notification to all clients"
    )
    await manager.broadcast_backend_startup()

async def get_websocket_health_status() -> dict:
    """
    Gibt den aktuellen Gesundheitsstatus aller WebSocket-Verbindungen zurück.
    """
    return await manager.get_connection_stats()


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
