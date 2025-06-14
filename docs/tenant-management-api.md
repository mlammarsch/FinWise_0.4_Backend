# Tenant Management API - Erweiterte Endpunkte

Diese Dokumentation beschreibt die erweiterten API-Endpunkte für die Mandanten-Verwaltung in FinWise.

## Übersicht

Die erweiterten Tenant Management APIs bieten folgende Funktionalitäten:
- Vollständige Mandanten-Löschung (inkl. Datei-Löschung)
- Mandanten-Datenbank-Reset
- SyncQueue-Bereinigung für Debugging/Wartung

## API-Endpunkte

### 1. Vollständige Mandanten-Löschung

**Endpunkt:** `DELETE /tenants/{tenant_id}/complete`

**Beschreibung:** Löscht einen Mandanten vollständig aus dem System, einschließlich:
- Mandanten-Eintrag aus der Haupt-Datenbank
- Entsprechende SQLite-Datei aus `tenant_databases/`
- WebSocket-Benachrichtigungen an andere Clients

**Parameter:**
- `tenant_id` (path): UUID des zu löschenden Mandanten
- `user_id` (query): UUID des Benutzers für Autorisierung

**Autorisierung:** Nur der Owner (Ersteller) des Mandanten kann ihn löschen.

**Response:**
```json
{
  "uuid": "tenant-uuid",
  "name": "Tenant Name",
  "user_id": "user-uuid",
  "createdAt": "2025-06-14T09:00:00Z",
  "updatedAt": "2025-06-14T09:00:00Z"
}
```

**Fehler-Codes:**
- `404`: Mandant nicht gefunden
- `403`: Benutzer nicht autorisiert
- `500`: Unerwarteter Fehler

**Beispiel:**
```bash
curl -X DELETE "http://localhost:8000/tenants/123e4567-e89b-12d3-a456-426614174000/complete?user_id=user-uuid-123"
```

### 2. Mandanten-Datenbank-Reset

**Endpunkt:** `POST /tenants/{tenant_id}/reset-database`

**Beschreibung:** Setzt die Mandanten-Datenbank zurück:
- Löscht alle Inhalte aller Tabellen in der Mandanten-DB
- Führt Initial-Setup durch (wie bei Mandanten-Erstellung)
- Behält Mandanten-Eintrag in Haupt-DB bei

**Parameter:**
- `tenant_id` (path): UUID des Mandanten
- `user_id` (query): UUID des Benutzers für Autorisierung

**Autorisierung:** Nur der Owner des Mandanten kann die DB zurücksetzen.

**Response:**
```json
{
  "message": "Database for tenant 123e4567-e89b-12d3-a456-426614174000 has been successfully reset",
  "tenant_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Fehler-Codes:**
- `404`: Mandant nicht gefunden
- `403`: Benutzer nicht autorisiert
- `500`: Unerwarteter Fehler

**Beispiel:**
```bash
curl -X POST "http://localhost:8000/tenants/123e4567-e89b-12d3-a456-426614174000/reset-database?user_id=user-uuid-123"
```

### 3. SyncQueue-Bereinigung

**Endpunkt:** `DELETE /tenants/{tenant_id}/sync-queue`

**Beschreibung:** Löscht alle SyncQueue-Einträge für den Mandanten.

**⚠️ WARNUNG:** Diese Operation kann zu Datenverlust führen, wenn noch nicht synchronisierte Änderungen in der Queue stehen! Nur für Debugging/Wartung verwenden.

**Parameter:**
- `tenant_id` (path): UUID des Mandanten
- `user_id` (query): UUID des Benutzers für Autorisierung

**Autorisierung:** Nur der Owner des Mandanten kann die SyncQueue leeren.

**Response:**
```json
{
  "message": "Sync queue for tenant 123e4567-e89b-12d3-a456-426614174000 has been successfully cleared",
  "tenant_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Fehler-Codes:**
- `404`: Mandant nicht gefunden
- `403`: Benutzer nicht autorisiert
- `500`: Unerwarteter Fehler

**Beispiel:**
```bash
curl -X DELETE "http://localhost:8000/tenants/123e4567-e89b-12d3-a456-426614174000/sync-queue?user_id=user-uuid-123"
```

## WebSocket-Benachrichtigungen

### Mandanten-Löschung

Bei vollständiger Mandanten-Löschung wird eine WebSocket-Nachricht an alle Clients des Mandanten gesendet:

```json
{
  "event_type": "data_update",
  "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
  "entity_type": "Tenant",
  "operation_type": "delete",
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "Tenant Name"
  }
}
```

### Datenbank-Reset

Bei Mandanten-Datenbank-Reset wird eine WebSocket-Nachricht gesendet:

```json
{
  "event_type": "data_update",
  "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
  "entity_type": "TenantDatabase",
  "operation_type": "reset",
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "Tenant Name",
    "action": "database_reset"
  }
}
```

## Sicherheitsüberlegungen

### Autorisierung
- Alle Endpunkte erfordern eine gültige `user_id`
- Nur der Owner (Ersteller) des Mandanten kann diese Operationen durchführen
- Autorisierung wird sowohl auf Router- als auch Service-Ebene validiert

### Datenschutz
- Vollständige Mandanten-Löschung entfernt alle Daten unwiderruflich
- Datenbank-Reset löscht alle Finanzdaten des Mandanten
- SyncQueue-Bereinigung kann zu Datenverlust führen

### Logging
- Alle kritischen Operationen werden umfassend geloggt
- Fehlerhafte Autorisierungsversuche werden protokolliert
- Performance-Metriken werden erfasst

## Implementierungsdetails

### Service-Layer
Die Business Logic ist im `TenantService` (`app/services/tenant_service.py`) implementiert:
- `delete_tenant_completely()`: Vollständige Mandanten-Löschung
- `reset_tenant_database()`: Datenbank-Reset
- `clear_sync_queue()`: SyncQueue-Bereinigung

### Datei-Management
- SQLite-Dateien werden aus `tenant_databases/` gelöscht
- Sichere Datei-Löschung mit Error-Handling
- Automatische Verzeichnis-Erstellung bei Bedarf

### WebSocket-Integration
- Automatische Benachrichtigungen über `ConnectionManager`
- Typisierte Nachrichten über Pydantic-Schemas
- Broadcast nur an betroffene Mandanten-Clients

## Testing

Umfassende Tests sind in `tests/test_tenant_management.py` implementiert:
- Unit-Tests für alle Endpunkte
- Autorisierungs-Tests
- Error-Handling-Tests
- Integration-Tests mit Test-Datenbank

**Tests ausführen:**
```bash
cd FinWise_0.4_BE
python -m pytest tests/test_tenant_management.py -v
```

## Verwendung im Frontend

Diese Backend-APIs bilden die Grundlage für Frontend-Funktionen wie:
- Mandanten-Löschung in der Admin-Oberfläche
- Datenbank-Reset für Entwicklung/Testing
- Sync-Queue-Debugging-Tools

Die Frontend-Integration erfolgt in einem separaten Task nach Abschluss der Backend-Implementierung.
