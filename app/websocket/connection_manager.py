from fastapi import WebSocket
from typing import Dict, Set, Optional
import json
from app.websocket.schemas import BackendStatusMessage # Import Pydantic model
from app.utils.logger import debugLog

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {} # tenant_id: {websockets}

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)
        debugLog(
            "ConnectionManager",
            f"WebSocket connected for tenant: {tenant_id}",
            details={"tenant_id": tenant_id, "client": websocket.client.host if websocket.client else "Unknown"}
        )

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].remove(websocket)
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

manager = ConnectionManager()
