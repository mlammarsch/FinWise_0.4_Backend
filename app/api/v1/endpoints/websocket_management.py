"""
API-Endpoints für WebSocket-Management und -Überwachung.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.websocket.utils import health_monitor, broadcaster, get_websocket_health, set_maintenance_mode
from app.websocket.connection_manager import manager
from app.websocket import endpoints as websocket_endpoints
from app.utils.logger import infoLog, debugLog, errorLog

router = APIRouter()

class MaintenanceModeRequest(BaseModel):
    enabled: bool
    message: Optional[str] = None

class SystemNotificationRequest(BaseModel):
    message: str
    notification_type: str = "info"  # info, warning, error

class BroadcastStatusRequest(BaseModel):
    status: str  # online, maintenance, shutdown, etc.

@router.get("/health", response_model=Dict[str, Any])
async def get_websocket_health_status():
    """
    Gibt den aktuellen Gesundheitsstatus aller WebSocket-Verbindungen zurück.
    """
    try:
        health_report = await get_websocket_health()
        debugLog(
            "WebSocketManagementAPI",
            "WebSocket health status requested",
            details={"overall_health": health_report.get("overall_health")}
        )
        return health_report
    except Exception as e:
        errorLog(
            "WebSocketManagementAPI",
            "Error retrieving WebSocket health status",
            details={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve health status")

@router.get("/connections", response_model=Dict[str, Any])
async def get_connection_statistics():
    """
    Gibt detaillierte Statistiken über aktive WebSocket-Verbindungen zurück.
    """
    try:
        stats = await manager.get_connection_stats()

        # Erweiterte Statistiken hinzufügen
        detailed_stats = {
            **stats,
            "active_tenants": list(manager.active_connections.keys()),
            "connections_per_tenant": {
                tenant_id: len(connections)
                for tenant_id, connections in manager.active_connections.items()
            }
        }

        debugLog(
            "WebSocketManagementAPI",
            "Connection statistics requested",
            details={"total_connections": stats["total_connections"], "tenant_count": stats["tenant_count"]}
        )

        return detailed_stats
    except Exception as e:
        errorLog(
            "WebSocketManagementAPI",
            "Error retrieving connection statistics",
            details={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve connection statistics")

@router.post("/maintenance")
async def set_maintenance_mode_endpoint(request: MaintenanceModeRequest):
    """
    Aktiviert oder deaktiviert den Wartungsmodus für alle WebSocket-Verbindungen.
    """
    try:
        await set_maintenance_mode(request.enabled, request.message)

        infoLog(
            "WebSocketManagementAPI",
            f"Maintenance mode {'enabled' if request.enabled else 'disabled'}",
            details={"enabled": request.enabled, "message": request.message}
        )

        return {
            "success": True,
            "maintenance_enabled": request.enabled,
            "message": request.message or ("Wartungsmodus aktiviert" if request.enabled else "Wartungsmodus beendet")
        }
    except Exception as e:
        errorLog(
            "WebSocketManagementAPI",
            "Error setting maintenance mode",
            details={"enabled": request.enabled, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to set maintenance mode")

@router.post("/broadcast/status")
async def broadcast_backend_status_endpoint(request: BroadcastStatusRequest):
    """
    Sendet eine Backend-Status-Nachricht an alle verbundenen Clients.
    """
    try:
        await websocket_endpoints.broadcast_backend_status(request.status)

        infoLog(
            "WebSocketManagementAPI",
            f"Backend status broadcasted: {request.status}",
            details={"status": request.status}
        )

        return {
            "success": True,
            "status": request.status,
            "message": f"Status '{request.status}' successfully broadcasted to all clients"
        }
    except Exception as e:
        errorLog(
            "WebSocketManagementAPI",
            "Error broadcasting backend status",
            details={"status": request.status, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to broadcast status")

@router.post("/broadcast/notification")
async def send_system_notification(request: SystemNotificationRequest):
    """
    Sendet eine Systembenachrichtigung an alle verbundenen Clients.
    """
    try:
        await broadcaster.broadcast_system_notification(request.message, request.notification_type)

        infoLog(
            "WebSocketManagementAPI",
            f"System notification sent: {request.notification_type}",
            details={"message": request.message, "type": request.notification_type}
        )

        return {
            "success": True,
            "message": request.message,
            "notification_type": request.notification_type
        }
    except Exception as e:
        errorLog(
            "WebSocketManagementAPI",
            "Error sending system notification",
            details={"message": request.message, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to send notification")

@router.post("/cleanup")
async def cleanup_stale_connections():
    """
    Bereinigt veraltete Verbindungsmetriken und führt Wartungsaufgaben durch.
    """
    try:
        await health_monitor.cleanup_stale_metrics()

        # Zusätzliche Bereinigungsaufgaben können hier hinzugefügt werden
        stats_before = await manager.get_connection_stats()

        infoLog(
            "WebSocketManagementAPI",
            "WebSocket cleanup completed",
            details={"connections_before": stats_before["total_connections"]}
        )

        stats_after = await manager.get_connection_stats()

        return {
            "success": True,
            "message": "Cleanup completed successfully",
            "stats_before": stats_before,
            "stats_after": stats_after
        }
    except Exception as e:
        errorLog(
            "WebSocketManagementAPI",
            "Error during WebSocket cleanup",
            details={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to perform cleanup")

@router.get("/ping-test/{tenant_id}")
async def test_tenant_ping(tenant_id: str):
    """
    Testet die Ping-Funktionalität für einen bestimmten Tenant.
    """
    try:
        if tenant_id not in manager.active_connections:
            raise HTTPException(status_code=404, detail=f"No active connections for tenant {tenant_id}")

        connections = manager.active_connections[tenant_id]
        ping_results = []

        for websocket in connections:
            try:
                ping_success = await manager.send_ping(websocket)
                ping_results.append({
                    "client": websocket.client.host if websocket.client else "Unknown",
                    "ping_success": ping_success,
                    "healthy": manager.connection_health.get(websocket, False)
                })
            except Exception as ping_error:
                ping_results.append({
                    "client": websocket.client.host if websocket.client else "Unknown",
                    "ping_success": False,
                    "error": str(ping_error)
                })

        debugLog(
            "WebSocketManagementAPI",
            f"Ping test completed for tenant {tenant_id}",
            details={"tenant_id": tenant_id, "connection_count": len(connections)}
        )

        return {
            "tenant_id": tenant_id,
            "connection_count": len(connections),
            "ping_results": ping_results
        }
    except HTTPException:
        raise
    except Exception as e:
        errorLog(
            "WebSocketManagementAPI",
            f"Error during ping test for tenant {tenant_id}",
            details={"tenant_id": tenant_id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to perform ping test")
