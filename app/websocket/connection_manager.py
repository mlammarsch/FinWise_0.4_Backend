from fastapi import WebSocket
from typing import Dict, Set
import json
from app.websocket.schemas import BackendStatusMessage # Import Pydantic model

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {} # tenant_id: {websockets}

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].remove(websocket)
            if not self.active_connections[tenant_id]: # Remove tenant_id if no connections left
                del self.active_connections[tenant_id]

    async def send_personal_message(self, message: str, websocket: WebSocket): # Keep as string for now
        await websocket.send_text(message)

    async def send_personal_json_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast_to_tenant(self, message: str, tenant_id: str): # Keep as string for now
        if tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                await connection.send_text(message)

    async def broadcast_json_to_tenant(self, message: dict, tenant_id: str):
        if tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                await connection.send_json(message)

    async def broadcast_to_all(self, message: str): # Keep as string for now
        for tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                await connection.send_text(message)

    async def broadcast_json_to_all(self, message: dict):
        for tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                await connection.send_json(message)

    async def broadcast_backend_status_message(self, status: str):
        """
        Broadcasts the backend status to all connected clients.
        Uses the BackendStatusMessage Pydantic model.
        """
        status_message = BackendStatusMessage(status=status)
        # Pydantic's model_dump_json() is preferred for direct JSON string conversion
        # For send_json, we need a dict, so use model_dump()
        await self.broadcast_json_to_all(status_message.model_dump())

manager = ConnectionManager()
