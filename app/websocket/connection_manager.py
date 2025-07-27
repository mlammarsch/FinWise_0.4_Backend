from fastapi import WebSocket
from typing import Dict, Set, Optional
import json
import asyncio
from app.websocket.schemas import BackendStatusMessage
from app.utils.logger import debugLog, infoLog, warnLog, errorLog

class ConnectionManager:
    """
    Verwaltet WebSocket-Verbindungen pro Tenant und sendet Nachrichten sowie regelmäßige Pings.
    """
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.ping_interval = 30
        self.ping_timeout = 10
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.connection_health: Dict[WebSocket, bool] = {}

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)
        self.connection_health[websocket] = True

        if self.heartbeat_task is None or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            infoLog("ConnectionManager", "Heartbeat-Task gestartet")

        debugLog(
            "ConnectionManager",
            f"WebSocket connected for tenant: {tenant_id}",
            details={"tenant_id": tenant_id, "client": websocket.client.host if websocket.client else "Unknown"}
        )

    def disconnect(self, websocket: WebSocket, tenant_id: str, reason: str = "Unknown"):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].discard(websocket)
            self.connection_health.pop(websocket, None)
            infoLog(
                "ConnectionManager",
                f"WebSocket disconnected for tenant: {tenant_id}. Reason: {reason}",
                details={"tenant_id": tenant_id, "client": websocket.client.host if websocket.client else "Unknown", "reason": reason}
            )
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]
                debugLog(
                    "ConnectionManager",
                    f"Removed tenant {tenant_id} from active connections (no connections left).",
                    details={"tenant_id": tenant_id}
                )

        if not any(self.active_connections.values()) and self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            infoLog("ConnectionManager", "Heartbeat-Task gestoppt - keine aktiven Verbindungen")

    async def close_connections_for_tenant(self, tenant_id: str, code: int = 1001, reason: str = "Tenant being deleted"):
        """Schließt alle aktiven WebSocket-Verbindungen für einen bestimmten Mandanten."""
        if tenant_id in self.active_connections:
            connections_to_close = list(self.active_connections[tenant_id]) # Kopie erstellen, da sich das Set während der Iteration ändert
            infoLog(
                "ConnectionManager",
                f"Attempting to close {len(connections_to_close)} WebSocket connections for tenant {tenant_id}. Reason: {reason}",
                details={"tenant_id": tenant_id, "count": len(connections_to_close), "reason": reason}
            )
            for websocket in connections_to_close:
                client_info = websocket.client.host if websocket.client else "Unknown"
                log_details = {"tenant_id": tenant_id, "client": client_info, "code": code}

                try:
                    # Prüfen, ob der WebSocket überhaupt noch in einem Zustand ist, in dem er geschlossen werden kann/muss
                    # Starlette WebSocket states: CONNECTING, CONNECTED, DISCONNECTED
                    # websocket.client_state und websocket.application_state
                    if websocket.application_state is not None and hasattr(websocket.application_state, 'value'): # FastAPI/Starlette spezifisch
                        log_details["app_state_before_close"] = websocket.application_state.value
                    if websocket.client_state is not None and hasattr(websocket.client_state, 'value'):
                        log_details["client_state_before_close"] = websocket.client_state.value

                    if websocket.application_state is None or \
                       (hasattr(websocket.application_state, 'value') and websocket.application_state.value != 2) : # 2 for DISCONNECTED

                        debugLog("ConnectionManager", f"Attempting to close WebSocket.", log_details)
                        await websocket.close(code=code)
                        infoLog("ConnectionManager", f"Successfully sent close frame to WebSocket.", log_details)
                    else:
                        warnLog("ConnectionManager", f"WebSocket already in disconnected state or no application state. Skipping close().", log_details)

                except RuntimeError as e:
                    # Dieser Fehler tritt auf, wenn versucht wird, eine bereits geschlossene oder schließende Verbindung zu schließen.
                    # "Cannot call 'send' once a close message has been sent."
                    # "Unexpected ASGI message 'websocket.close', after sending 'websocket.close' or response already completed."
                    if "Cannot call 'send' once a close message has been sent" in str(e) or \
                       "Unexpected ASGI message 'websocket.close'" in str(e):
                        warnLog("ConnectionManager", f"RuntimeError (likely already closing/closed) while sending close frame: {e}", log_details)
                    else:
                        errorLog("ConnectionManager", f"Unhandled RuntimeError sending close frame: {e}", {**log_details, "error": str(e)})
                except Exception as e:
                    errorLog("ConnectionManager", f"Unexpected error sending close frame: {e}", {**log_details, "error_type": type(e).__name__, "error": str(e)})
                finally:
                    # Unabhängig vom Erfolg des close()-Aufrufs, die Verbindung aus der Verwaltung entfernen
                    self.disconnect(websocket, tenant_id, reason=f"Explicitly closed: {reason}")
        else:
            debugLog(
                "ConnectionManager",
                f"No active connections found for tenant {tenant_id} to close.",
                details={"tenant_id": tenant_id}
            )

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            # Prüfe WebSocket-Status vor dem Senden
            if websocket.application_state is not None and hasattr(websocket.application_state, 'value'):
                if websocket.application_state.value == 2:  # DISCONNECTED
                    warnLog(
                        "ConnectionManager",
                        "Cannot send personal message - WebSocket is disconnected",
                        details={"client": websocket.client.host if websocket.client else "Unknown"}
                    )
                    return

            await websocket.send_text(message)
            debugLog(
                "ConnectionManager",
                "Sent personal text message",
                details={"client": websocket.client.host if websocket.client else "Unknown", "message_length": len(message)}
            )
        except RuntimeError as e:
            if "Unexpected ASGI message 'websocket.send'" in str(e) or \
               "Cannot call 'send' once a close message has been sent" in str(e):
                warnLog(
                    "ConnectionManager",
                    f"WebSocket state error sending personal message: {e}",
                    details={"client": websocket.client.host if websocket.client else "Unknown", "error": str(e)}
                )
            else:
                errorLog(
                    "ConnectionManager",
                    f"Unexpected RuntimeError sending personal message: {e}",
                    details={"client": websocket.client.host if websocket.client else "Unknown", "error": str(e)}
                )
        except Exception as e:
            errorLog(
                "ConnectionManager",
                f"Unexpected error sending personal message: {e}",
                details={"client": websocket.client.host if websocket.client else "Unknown", "error_type": type(e).__name__, "error": str(e)}
            )

    async def send_personal_json_message(self, message: dict, websocket: WebSocket):
        try:
            # Prüfe WebSocket-Status vor dem Senden
            if websocket.application_state is not None and hasattr(websocket.application_state, 'value'):
                if websocket.application_state.value == 2:  # DISCONNECTED
                    warnLog(
                        "ConnectionManager",
                        "Cannot send personal JSON message - WebSocket is disconnected",
                        details={"client": websocket.client.host if websocket.client else "Unknown"}
                    )
                    return

            await websocket.send_json(message)
            debugLog(
                "ConnectionManager",
                "Sent personal JSON message",
                details={"client": websocket.client.host if websocket.client else "Unknown", "message_keys": list(message.keys())}
            )
        except RuntimeError as e:
            if "Unexpected ASGI message 'websocket.send'" in str(e) or \
               "Cannot call 'send' once a close message has been sent" in str(e):
                warnLog(
                    "ConnectionManager",
                    f"WebSocket state error sending personal JSON message: {e}",
                    details={"client": websocket.client.host if websocket.client else "Unknown", "error": str(e)}
                )
            else:
                errorLog(
                    "ConnectionManager",
                    f"Unexpected RuntimeError sending personal JSON message: {e}",
                    details={"client": websocket.client.host if websocket.client else "Unknown", "error": str(e)}
                )
        except Exception as e:
            errorLog(
                "ConnectionManager",
                f"Unexpected error sending personal JSON message: {e}",
                details={"client": websocket.client.host if websocket.client else "Unknown", "error_type": type(e).__name__, "error": str(e)}
            )

    async def broadcast_to_tenant(self, message: str, tenant_id: str):
        if tenant_id in self.active_connections:
            sent_to_count = 0
            failed_connections = []

            for connection in self.active_connections[tenant_id].copy():  # Kopie für sichere Iteration
                try:
                    # Prüfe WebSocket-Status vor dem Senden
                    if connection.application_state is not None and hasattr(connection.application_state, 'value'):
                        if connection.application_state.value == 2:  # DISCONNECTED
                            warnLog(
                                "ConnectionManager",
                                f"Skipping send to disconnected WebSocket for tenant {tenant_id}",
                                details={"client": connection.client.host if connection.client else "Unknown"}
                            )
                            failed_connections.append(connection)
                            continue

                    await connection.send_text(message)
                    sent_to_count += 1

                except RuntimeError as e:
                    if "Unexpected ASGI message 'websocket.send'" in str(e) or \
                       "Cannot call 'send' once a close message has been sent" in str(e):
                        warnLog(
                            "ConnectionManager",
                            f"WebSocket state error broadcasting to tenant {tenant_id}: {e}",
                            details={"client": connection.client.host if connection.client else "Unknown", "error": str(e)}
                        )
                        failed_connections.append(connection)
                    else:
                        errorLog(
                            "ConnectionManager",
                            f"Unexpected RuntimeError broadcasting to tenant {tenant_id}: {e}",
                            details={"client": connection.client.host if connection.client else "Unknown", "error": str(e)}
                        )
                        failed_connections.append(connection)
                except Exception as e:
                    errorLog(
                        "ConnectionManager",
                        f"Unexpected error broadcasting to tenant {tenant_id}: {e}",
                        details={"client": connection.client.host if connection.client else "Unknown", "error_type": type(e).__name__, "error": str(e)}
                    )
                    failed_connections.append(connection)

            # Entferne fehlgeschlagene Verbindungen
            for failed_connection in failed_connections:
                self.disconnect(failed_connection, tenant_id, reason="Broadcast failed - connection state error")

            debugLog(
                "ConnectionManager",
                f"Broadcasted text message to tenant: {tenant_id}",
                details={
                    "tenant_id": tenant_id,
                    "message_length": len(message),
                    "connection_count": len(self.active_connections.get(tenant_id, [])),
                    "sent_to_count": sent_to_count,
                    "failed_count": len(failed_connections)
                }
            )

    async def broadcast_json_to_tenant(self, message: dict, tenant_id: str, exclude_websocket: Optional[WebSocket] = None):
        if tenant_id in self.active_connections:
            sent_to_count = 0
            failed_connections = []

            for connection in self.active_connections[tenant_id].copy():  # Kopie erstellen für sichere Iteration
                if exclude_websocket and connection == exclude_websocket:
                    continue

                try:
                    # Prüfe WebSocket-Status vor dem Senden
                    if connection.application_state is not None and hasattr(connection.application_state, 'value'):
                        # 2 = DISCONNECTED state in Starlette/FastAPI
                        if connection.application_state.value == 2:
                            warnLog(
                                "ConnectionManager",
                                f"Skipping send to disconnected WebSocket for tenant {tenant_id}",
                                details={"client": connection.client.host if connection.client else "Unknown", "app_state": connection.application_state.value}
                            )
                            failed_connections.append(connection)
                            continue

                    debugLog(
                        "ConnectionManager",
                        f"Attempting to send JSON to {connection.client.host if connection.client else 'Unknown'} for tenant {tenant_id} via broadcast_json_to_tenant",
                        details={"message_type": type(message), "message_content_preview": str(message)[:200]}
                    )
                    await connection.send_json(message)
                    sent_to_count += 1

                except RuntimeError as e:
                    # Fange spezifische WebSocket-State-Fehler ab
                    if "Unexpected ASGI message 'websocket.send'" in str(e) or \
                       "Cannot call 'send' once a close message has been sent" in str(e):
                        warnLog(
                            "ConnectionManager",
                            f"WebSocket state error sending to tenant {tenant_id}: {e}",
                            details={"client": connection.client.host if connection.client else "Unknown", "error": str(e)}
                        )
                        failed_connections.append(connection)
                    else:
                        errorLog(
                            "ConnectionManager",
                            f"Unexpected RuntimeError sending to tenant {tenant_id}: {e}",
                            details={"client": connection.client.host if connection.client else "Unknown", "error": str(e)}
                        )
                        failed_connections.append(connection)
                except Exception as e:
                    errorLog(
                        "ConnectionManager",
                        f"Unexpected error sending JSON to tenant {tenant_id}: {e}",
                        details={"client": connection.client.host if connection.client else "Unknown", "error_type": type(e).__name__, "error": str(e)}
                    )
                    failed_connections.append(connection)

            # Entferne fehlgeschlagene Verbindungen aus der aktiven Liste
            for failed_connection in failed_connections:
                self.disconnect(failed_connection, tenant_id, reason="Send failed - connection state error")

            debugLog(
                "ConnectionManager",
                f"Broadcasted JSON message to tenant: {tenant_id}",
                details={
                    "tenant_id": tenant_id,
                    "message_keys": list(message.keys()),
                    "connection_count": len(self.active_connections.get(tenant_id, [])),
                    "sent_to_count": sent_to_count,
                    "failed_count": len(failed_connections),
                    "excluded_a_connection": bool(exclude_websocket)
                }
            )

    async def broadcast_to_all(self, message: str):
        for tenant_id_loop in self.active_connections:
            for connection in self.active_connections[tenant_id_loop]:
                await connection.send_text(message)
        debugLog(
            "ConnectionManager",
            "Broadcasted text message to all tenants",
            details={"message_length": len(message), "tenant_count": len(self.active_connections)}
        )

    async def broadcast_json_to_all(self, message: dict):
        for tenant_id_loop in self.active_connections:
            for connection in self.active_connections[tenant_id_loop]:
                await connection.send_json(message)
        debugLog(
            "ConnectionManager",
            "Broadcasted JSON message to all tenants",
            details={"message_keys": list(message.keys()), "tenant_count": len(self.active_connections)}
        )

    async def broadcast_backend_status_message(self, status: str):
        # DIAGNOSTIC LOG: Check active connections before broadcast
        total_connections = sum(len(connections) for connections in self.active_connections.values())
        debugLog("ConnectionManager", f"DIAGNOSIS: Broadcasting status '{status}' to {total_connections} connections across {len(self.active_connections)} tenants")

        status_message = BackendStatusMessage(status=status)
        await self.broadcast_json_to_all(status_message.model_dump())
        debugLog("ConnectionManager", f"Broadcasted backend status: {status}", details={"status": status})


    async def _heartbeat_loop(self):
        infoLog("ConnectionManager", "Heartbeat-Loop gestartet")
        while True:
            try:
                await asyncio.sleep(self.ping_interval)
                if not any(self.active_connections.values()):
                    debugLog("ConnectionManager", "Keine aktiven Verbindungen - Heartbeat-Loop beendet")
                    break

                all_websockets = []
                websocket_to_tenant = {}

                for tenant_id, websockets in self.active_connections.items():
                    for ws in websockets.copy():
                        all_websockets.append(ws)
                        websocket_to_tenant[ws] = tenant_id

                debugLog("ConnectionManager", f"Heartbeat-Check für {len(all_websockets)} Verbindungen",
                         details={"connection_count": len(all_websockets), "tenant_count": len(self.active_connections)})

                ping_message = {"type": "ping", "timestamp": asyncio.get_event_loop().time()}
                for ws in all_websockets:
                    try:
                        await ws.send_json(ping_message)
                    except Exception as e:
                        tenant_id = websocket_to_tenant.get(ws)
                        if tenant_id:
                            warnLog("ConnectionManager", f"Fehler beim Senden des Pings an WebSocket für Tenant {tenant_id}: {e}",
                                    details={"tenant_id": tenant_id, "client": ws.client.host if ws.client else "Unknown", "error": str(e)})
                            self.disconnect(ws, tenant_id, reason=f"Ping send failed: {e}")
                            try:
                                await ws.close(code=1001)
                            except Exception:
                                pass # Ignore errors on close, as the connection is already likely dead
            except asyncio.CancelledError:
                infoLog("ConnectionManager", "Heartbeat-Loop wurde abgebrochen")
                break
            except Exception as e:
                errorLog("ConnectionManager", "Fehler im Heartbeat-Loop", details={"error": str(e)})
                await asyncio.sleep(5)

    async def broadcast_backend_startup(self):
        if any(self.active_connections.values()):
            await self.broadcast_backend_status_message("startup")
            infoLog("ConnectionManager", "Backend-Startup-Nachricht an alle Clients gesendet",
                    details={"tenant_count": len(self.active_connections)})
        else:
            debugLog("ConnectionManager", "Keine aktiven Verbindungen für Startup-Broadcast")

    async def get_connection_stats(self) -> dict:
        total_connections = sum(len(connections) for connections in self.active_connections.values())
        healthy_connections = sum(1 for ws, healthy in self.connection_health.items() if healthy)

        return {
            "total_connections": total_connections,
            "healthy_connections": healthy_connections,
            "tenant_count": len(self.active_connections),
            "heartbeat_active": self.heartbeat_task is not None and not self.heartbeat_task.done()
        }

manager = ConnectionManager()
