from fastapi import WebSocket
from typing import Dict, Set, Optional
import json
import asyncio
from app.websocket.schemas import BackendStatusMessage # Import Pydantic model
from app.utils.logger import debugLog, infoLog, warnLog, errorLog

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {} # tenant_id: {websockets}
        self.ping_interval = 30  # Ping-Intervall in Sekunden
        self.ping_timeout = 10   # Timeout für Pong-Antwort in Sekunden
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.connection_health: Dict[WebSocket, bool] = {}  # Verfolgt Gesundheit der Verbindungen

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)
        self.connection_health[websocket] = True  # Neue Verbindung als gesund markieren

        # Starte Heartbeat-Task wenn es die erste Verbindung ist
        if self.heartbeat_task is None or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            infoLog("ConnectionManager", "Heartbeat-Task gestartet")

        debugLog(
            "ConnectionManager",
            f"WebSocket connected for tenant: {tenant_id}",
            details={"tenant_id": tenant_id, "client": websocket.client.host if websocket.client else "Unknown"}
        )

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].discard(websocket)  # discard ist sicherer als remove
            self.connection_health.pop(websocket, None)  # Entferne aus Health-Tracking
            debugLog(
                "ConnectionManager",
                f"WebSocket disconnected for tenant: {tenant_id}",
                details={"tenant_id": tenant_id, "client": websocket.client.host if websocket.client else "Unknown"}
            )
            if not self.active_connections[tenant_id]: # Remove tenant_id if no connections left
                del self.active_connections[tenant_id]
                debugLog(
                    "ConnectionManager",
                    f"Removed tenant {tenant_id} from active connections (no connections left).",
                    details={"tenant_id": tenant_id}
                )

        # Stoppe Heartbeat-Task wenn keine Verbindungen mehr vorhanden sind
        if not any(self.active_connections.values()) and self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            infoLog("ConnectionManager", "Heartbeat-Task gestoppt - keine aktiven Verbindungen")

    async def send_personal_message(self, message: str, websocket: WebSocket): # Keep as string for now
        await websocket.send_text(message)
        debugLog(
            "ConnectionManager",
            "Sent personal text message",
            details={"client": websocket.client.host if websocket.client else "Unknown", "message_length": len(message)}
        )

    async def send_personal_json_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)
        debugLog(
            "ConnectionManager",
            "Sent personal JSON message",
            details={"client": websocket.client.host if websocket.client else "Unknown", "message_keys": list(message.keys())}
        )

    async def broadcast_to_tenant(self, message: str, tenant_id: str): # Keep as string for now
        if tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                await connection.send_text(message)
            debugLog(
                "ConnectionManager",
                f"Broadcasted text message to tenant: {tenant_id}",
                details={"tenant_id": tenant_id, "message_length": len(message), "connection_count": len(self.active_connections[tenant_id])}
            )

    async def broadcast_json_to_tenant(self, message: dict, tenant_id: str, exclude_websocket: Optional[WebSocket] = None):
        if tenant_id in self.active_connections:
            sent_to_count = 0
            for connection in self.active_connections[tenant_id]:
                if exclude_websocket and connection == exclude_websocket:
                    continue
                await connection.send_json(message)
                sent_to_count += 1
            debugLog(
                "ConnectionManager",
                f"Broadcasted JSON message to tenant: {tenant_id}",
                details={"tenant_id": tenant_id, "message_keys": list(message.keys()), "connection_count": len(self.active_connections[tenant_id]), "sent_to_count": sent_to_count, "excluded_a_connection": bool(exclude_websocket)}
            )

    async def broadcast_to_all(self, message: str): # Keep as string for now
        for tenant_id_loop in self.active_connections: # Renamed tenant_id to avoid conflict
            for connection in self.active_connections[tenant_id_loop]:
                await connection.send_text(message)
        debugLog(
            "ConnectionManager",
            "Broadcasted text message to all tenants",
            details={"message_length": len(message), "tenant_count": len(self.active_connections)}
        )

    async def broadcast_json_to_all(self, message: dict):
        for tenant_id_loop in self.active_connections: # Renamed tenant_id to avoid conflict
            for connection in self.active_connections[tenant_id_loop]:
                await connection.send_json(message)
        debugLog(
            "ConnectionManager",
            "Broadcasted JSON message to all tenants",
            details={"message_keys": list(message.keys()), "tenant_count": len(self.active_connections)}
        )

    async def broadcast_backend_status_message(self, status: str):
        """
        Broadcasts the backend status to all connected clients.
        Uses the BackendStatusMessage Pydantic model.
        """
        status_message = BackendStatusMessage(status=status)
        # Pydantic's model_dump_json() is preferred for direct JSON string conversion
        # For send_json, we need a dict, so use model_dump()
        await self.broadcast_json_to_all(status_message.model_dump())
        debugLog(
            "ConnectionManager",
            f"Broadcasted backend status: {status}",
            details={"status": status}
        )

    async def send_ping(self, websocket: WebSocket) -> bool:
        """
        Sendet einen Ping an eine WebSocket-Verbindung und wartet auf Pong.
        Gibt True zurück wenn Pong empfangen wurde, False bei Timeout oder Fehler.
        """
        try:
            await websocket.ping()
            # Warte auf Pong mit Timeout
            await asyncio.wait_for(websocket.pong(), timeout=self.ping_timeout)
            self.connection_health[websocket] = True
            return True
        except asyncio.TimeoutError:
            warnLog(
                "ConnectionManager",
                "Ping timeout - keine Pong-Antwort erhalten",
                details={"client": websocket.client.host if websocket.client else "Unknown", "timeout": self.ping_timeout}
            )
            self.connection_health[websocket] = False
            return False
        except Exception as e:
            errorLog(
                "ConnectionManager",
                "Fehler beim Ping-Versand",
                details={"client": websocket.client.host if websocket.client else "Unknown", "error": str(e)}
            )
            self.connection_health[websocket] = False
            return False

    async def _heartbeat_loop(self):
        """
        Periodischer Heartbeat-Loop der Pings an alle Verbindungen sendet
        und ungesunde Verbindungen entfernt.
        """
        infoLog("ConnectionManager", "Heartbeat-Loop gestartet")

        while True:
            try:
                await asyncio.sleep(self.ping_interval)

                if not any(self.active_connections.values()):
                    debugLog("ConnectionManager", "Keine aktiven Verbindungen - Heartbeat-Loop beendet")
                    break

                # Sammle alle WebSocket-Verbindungen
                all_websockets = []
                websocket_to_tenant = {}

                for tenant_id, websockets in self.active_connections.items():
                    for ws in websockets.copy():  # copy() um Änderungen während Iteration zu vermeiden
                        all_websockets.append(ws)
                        websocket_to_tenant[ws] = tenant_id

                debugLog(
                    "ConnectionManager",
                    f"Heartbeat-Check für {len(all_websockets)} Verbindungen",
                    details={"connection_count": len(all_websockets), "tenant_count": len(self.active_connections)}
                )

                # Ping alle Verbindungen parallel
                ping_tasks = [self.send_ping(ws) for ws in all_websockets]
                if ping_tasks:
                    ping_results = await asyncio.gather(*ping_tasks, return_exceptions=True)

                    # Entferne ungesunde Verbindungen
                    for ws, result in zip(all_websockets, ping_results):
                        if isinstance(result, Exception) or result is False:
                            tenant_id = websocket_to_tenant.get(ws)
                            if tenant_id:
                                warnLog(
                                    "ConnectionManager",
                                    f"Entferne ungesunde WebSocket-Verbindung für Tenant {tenant_id}",
                                    details={"tenant_id": tenant_id, "client": ws.client.host if ws.client else "Unknown"}
                                )
                                self.disconnect(ws, tenant_id)
                                try:
                                    await ws.close()
                                except Exception:
                                    pass  # Verbindung könnte bereits geschlossen sein

            except asyncio.CancelledError:
                infoLog("ConnectionManager", "Heartbeat-Loop wurde abgebrochen")
                break
            except Exception as e:
                errorLog(
                    "ConnectionManager",
                    "Fehler im Heartbeat-Loop",
                    details={"error": str(e)}
                )
                # Warte kurz bevor der Loop fortgesetzt wird
                await asyncio.sleep(5)

    async def broadcast_backend_startup(self):
        """
        Sendet eine Startup-Nachricht an alle verbundenen Clients.
        """
        if any(self.active_connections.values()):
            await self.broadcast_backend_status_message("startup")
            infoLog(
                "ConnectionManager",
                "Backend-Startup-Nachricht an alle Clients gesendet",
                details={"tenant_count": len(self.active_connections)}
            )
        else:
            debugLog("ConnectionManager", "Keine aktiven Verbindungen für Startup-Broadcast")

    async def get_connection_stats(self) -> dict:
        """
        Gibt Statistiken über aktive Verbindungen zurück.
        """
        total_connections = sum(len(connections) for connections in self.active_connections.values())
        healthy_connections = sum(1 for ws, healthy in self.connection_health.items() if healthy)

        return {
            "total_connections": total_connections,
            "healthy_connections": healthy_connections,
            "tenant_count": len(self.active_connections),
            "heartbeat_active": self.heartbeat_task is not None and not self.heartbeat_task.done()
        }

manager = ConnectionManager()
