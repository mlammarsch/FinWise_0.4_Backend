from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class SyncLog(Base):
    """
    Modell für Sync-Protokollierung und Audit-Zwecke.
    """
    __tablename__ = "sync_logs"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)  # Account, AccountGroup, etc.
    entity_id = Column(String, nullable=False)
    operation_type = Column(String, nullable=False)  # create, update, delete
    sync_direction = Column(String, nullable=False)  # client_to_server, server_to_client
    status = Column(String, nullable=False)  # success, failed, conflict
    error_message = Column(Text, nullable=True)
    payload_checksum = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    metadata = Column(JSON, nullable=True)  # Zusätzliche Metadaten als JSON

class SyncConflict(Base):
    """
    Modell für Sync-Konflikte zwischen Client und Server.
    """
    __tablename__ = "sync_conflicts"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    local_checksum = Column(String, nullable=False)
    server_checksum = Column(String, nullable=False)
    local_last_modified = Column(DateTime, nullable=True)
    server_last_modified = Column(DateTime, nullable=True)
    conflict_type = Column(String, nullable=False)  # data_mismatch, version_conflict, etc.
    resolution_status = Column(String, default="pending")  # pending, resolved_local, resolved_server, resolved_manual
    resolution_strategy = Column(String, nullable=True)  # last_write_wins, manual_merge, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String, nullable=True)  # user_id or system
    conflict_data = Column(JSON, nullable=True)  # Detaillierte Konfliktdaten

class SyncMetrics(Base):
    """
    Modell für Sync-Metriken und Performance-Tracking.
    """
    __tablename__ = "sync_metrics"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    sync_session_id = Column(String, nullable=False)  # Eindeutige Session-ID für zusammengehörige Sync-Operationen
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    entities_processed = Column(Integer, default=0)
    entities_successful = Column(Integer, default=0)
    entities_failed = Column(Integer, default=0)
    conflicts_detected = Column(Integer, default=0)
    sync_type = Column(String, nullable=False)  # manual, automatic, initial_load
    trigger_source = Column(String, nullable=True)  # websocket, api, scheduled
    success = Column(Boolean, default=False)
    error_summary = Column(Text, nullable=True)
    performance_data = Column(JSON, nullable=True)  # Detaillierte Performance-Daten

class SyncCheckpoint(Base):
    """
    Modell für Sync-Checkpoints zur Wiederherstellung nach Fehlern.
    """
    __tablename__ = "sync_checkpoints"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    checkpoint_type = Column(String, nullable=False)  # full_sync, incremental_sync
    last_sync_time = Column(DateTime, nullable=False)
    entity_counts = Column(JSON, nullable=True)  # Anzahl der Entitäten pro Typ
    data_checksums = Column(JSON, nullable=True)  # Gesamtchecksummen pro Entitätstyp
    sync_version = Column(String, nullable=True)  # Version des Sync-Protokolls
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_valid = Column(Boolean, default=True)
    validation_errors = Column(JSON, nullable=True)
