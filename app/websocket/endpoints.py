from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from app.api import deps # Annahme: deps.py existiert und enthält get_db und get_current_active_user
from app.websocket.connection_manager import manager
from app.models.user_tenant_models import User

router = APIRouter()

@router.websocket("/ws/{tenant_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    # current_user: User = Depends(deps.get_current_active_user), # Vorerst auskommentiert, um Komplexität zu reduzieren
    # db: Session = Depends(deps.get_db) # Vorerst auskommentiert
):
    # Hier könnte eine Überprüfung erfolgen, ob der current_user Zugriff auf den tenant_id hat.
    # Fürs Erste wird dies vereinfacht.
    await manager.connect(websocket, tenant_id)
    try:
        await manager.send_personal_message(f"Backend online for tenant {tenant_id}", websocket)
        while True:
            data = await websocket.receive_text()
            # Hier könnte die empfangene Nachricht verarbeitet werden.
            # Beispiel: await manager.broadcast_to_tenant(f"Client von Tenant {tenant_id} sagt: {data}", tenant_id)
            # Für die Basisfunktionalität ist dies vorerst nicht notwendig.
            # Stattdessen senden wir eine Bestätigung zurück.
            await manager.send_personal_message(f"Nachricht empfangen: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)
        # Optional: Benachrichtige andere Clients im selben Tenant über den Disconnect
        # await manager.broadcast_to_tenant(f"Ein Client von Tenant {tenant_id} hat die Verbindung getrennt.", tenant_id)
    except Exception as e:
        # Loggen des Fehlers wäre hier sinnvoll
        print(f"Error in websocket connection for tenant {tenant_id}: {e}")
        manager.disconnect(websocket, tenant_id)

# Zukünftige Erweiterung für Datenänderungsbenachrichtigungen
async def notify_data_change(tenant_id: str, entity_type: str, entity_id: str, action: str, data: dict):
    """
    Sendet eine Benachrichtigung über Datenänderungen an alle Clients eines Tenants.
    Beispiel: notify_data_change("tenant_xyz", "account", "acc_123", "updated", {"balance": 1500})
    """
    message = {
        "type": "data_update",
        "entity": entity_type,
        "id": entity_id,
        "action": action, # "created", "updated", "deleted"
        "payload": data
    }
    await manager.broadcast_to_tenant(str(message), tenant_id)

# Zukünftige Erweiterung für Online/Offline Status
async def broadcast_backend_status(status: str): # "online" or "offline"
    """
    Sendet den Backend-Status an alle verbundenen Clients.
    """
    message = {
        "type": "backend_status",
        "status": status
    }
    await manager.broadcast_to_all(str(message))
