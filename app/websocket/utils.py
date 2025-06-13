"""
WebSocket-Utilities für erweiterte Funktionalitäten wie Health-Monitoring und Broadcasting.
"""

import asyncio
from typing import Dict, List, Optional
from fastapi import WebSocket
from app.websocket.connection_manager import manager
from app.websocket.schemas import BackendStatusMessage
from app.utils.logger import infoLog, debugLog, errorLog, warnLog

class WebSocketHealthMonitor:
    """
    Überwacht die Gesundheit von WebSocket-Verbindungen und bietet erweiterte Monitoring-Funktionen.
    """

    def __init__(self):
        self.connection_metrics: Dict[str, Dict] = {}  # tenant_id -> metrics
        self.last_health_check: Optional[float] = None

    async def record_connection_event(self, tenant_id: str, event_type: str, websocket: WebSocket = None):
        """
        Zeichnet Verbindungsereignisse für Monitoring auf.
        """
        if tenant_id not in self.connection_metrics:
            self.connection_metrics[tenant_id] = {
                "connections": 0,
                "disconnections": 0,
                "ping_failures": 0,
                "last_activity": None,
                "total_messages": 0
            }

        metrics = self.connection_metrics[tenant_id]

        if event_type == "connect":
            metrics["connections"] += 1
            metrics["last_activity"] = asyncio.get_event_loop().time()
            debugLog(
                "WebSocketHealthMonitor",
                f"Recorded connection event for tenant {tenant_id}",
                details={"event": event_type, "total_connections": metrics["connections"]}
            )
        elif event_type == "disconnect":
            metrics["disconnections"] += 1
            debugLog(
                "WebSocketHealthMonitor",
                f"Recorded disconnection event for tenant {tenant_id}",
                details={"event": event_type, "total_disconnections": metrics["disconnections"]}
            )
        elif event_type == "ping_failure":
            metrics["ping_failures"] += 1
            warnLog(
                "WebSocketHealthMonitor",
                f"Recorded ping failure for tenant {tenant_id}",
                details={"event": event_type, "total_ping_failures": metrics["ping_failures"]}
            )
        elif event_type == "message":
            metrics["total_messages"] += 1
            metrics["last_activity"] = asyncio.get_event_loop().time()

    async def get_health_report(self) -> Dict:
        """
        Erstellt einen umfassenden Gesundheitsbericht aller WebSocket-Verbindungen.
        """
        connection_stats = await manager.get_connection_stats()

        health_report = {
            "overall_health": "healthy" if connection_stats["healthy_connections"] == connection_stats["total_connections"] else "degraded",
            "connection_stats": connection_stats,
            "tenant_metrics": self.connection_metrics,
            "heartbeat_status": "active" if connection_stats["heartbeat_active"] else "inactive",
            "timestamp": asyncio.get_event_loop().time()
        }

        # Bestimme Gesamtgesundheit basierend auf verschiedenen Faktoren
        if connection_stats["total_connections"] == 0:
            health_report["overall_health"] = "no_connections"
        elif connection_stats["healthy_connections"] < connection_stats["total_connections"] * 0.8:
            health_report["overall_health"] = "critical"
        elif connection_stats["healthy_connections"] < connection_stats["total_connections"]:
            health_report["overall_health"] = "degraded"

        return health_report

    async def cleanup_stale_metrics(self, max_age_hours: int = 24):
        """
        Bereinigt veraltete Metriken für Tenants ohne aktive Verbindungen.
        """
        current_time = asyncio.get_event_loop().time()
        max_age_seconds = max_age_hours * 3600

        stale_tenants = []
        for tenant_id, metrics in self.connection_metrics.items():
            if tenant_id not in manager.active_connections:
                last_activity = metrics.get("last_activity", 0)
                if current_time - last_activity > max_age_seconds:
                    stale_tenants.append(tenant_id)

        for tenant_id in stale_tenants:
            del self.connection_metrics[tenant_id]
            debugLog(
                "WebSocketHealthMonitor",
                f"Cleaned up stale metrics for tenant {tenant_id}",
                details={"tenant_id": tenant_id, "age_hours": max_age_hours}
            )

class WebSocketBroadcaster:
    """
    Erweiterte Broadcasting-Funktionalitäten für WebSocket-Nachrichten.
    """

    @staticmethod
    async def broadcast_system_notification(message: str, notification_type: str = "info"):
        """
        Sendet eine Systembenachrichtigung an alle verbundenen Clients.
        """
        notification = {
            "type": "system_notification",
            "notification_type": notification_type,
            "message": message,
            "timestamp": asyncio.get_event_loop().time()
        }

        await manager.broadcast_json_to_all(notification)
        infoLog(
            "WebSocketBroadcaster",
            f"Broadcasted system notification: {notification_type}",
            details={"message": message, "type": notification_type}
        )

    @staticmethod
    async def broadcast_maintenance_mode(enabled: bool, message: str = None):
        """
        Benachrichtigt alle Clients über Wartungsmodus-Änderungen.
        """
        status = "maintenance" if enabled else "online"
        maintenance_notification = {
            "type": "maintenance_notification",
            "maintenance_enabled": enabled,
            "message": message or ("Wartungsmodus aktiviert" if enabled else "Wartungsmodus beendet"),
            "timestamp": asyncio.get_event_loop().time()
        }

        # Sende sowohl Status- als auch spezifische Wartungsbenachrichtigung
        await manager.broadcast_backend_status_message(status)
        await manager.broadcast_json_to_all(maintenance_notification)

        infoLog(
            "WebSocketBroadcaster",
            f"Broadcasted maintenance mode change: {enabled}",
            details={"enabled": enabled, "message": message}
        )

    @staticmethod
    async def broadcast_to_tenant_with_retry(tenant_id: str, message: dict, max_retries: int = 3):
        """
        Sendet eine Nachricht an einen Tenant mit Wiederholungslogik.
        """
        for attempt in range(max_retries):
            try:
                await manager.broadcast_json_to_tenant(message, tenant_id)
                debugLog(
                    "WebSocketBroadcaster",
                    f"Successfully sent message to tenant {tenant_id} on attempt {attempt + 1}",
                    details={"tenant_id": tenant_id, "attempt": attempt + 1}
                )
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    warnLog(
                        "WebSocketBroadcaster",
                        f"Failed to send message to tenant {tenant_id} on attempt {attempt + 1}, retrying...",
                        details={"tenant_id": tenant_id, "attempt": attempt + 1, "error": str(e)}
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                else:
                    errorLog(
                        "WebSocketBroadcaster",
                        f"Failed to send message to tenant {tenant_id} after {max_retries} attempts",
                        details={"tenant_id": tenant_id, "max_retries": max_retries, "error": str(e)}
                    )
                    return False
        return False

# Globale Instanzen
health_monitor = WebSocketHealthMonitor()
broadcaster = WebSocketBroadcaster()

# Convenience-Funktionen für einfache Nutzung
async def get_websocket_health() -> Dict:
    """Gibt den aktuellen WebSocket-Gesundheitsstatus zurück."""
    return await health_monitor.get_health_report()

async def broadcast_system_message(message: str, msg_type: str = "info"):
    """Sendet eine Systemnachricht an alle Clients."""
    await broadcaster.broadcast_system_notification(message, msg_type)

async def set_maintenance_mode(enabled: bool, message: str = None):
    """Aktiviert oder deaktiviert den Wartungsmodus."""
    await broadcaster.broadcast_maintenance_mode(enabled, message)
