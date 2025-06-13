from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from app.models.sync_models import SyncLog, SyncConflict, SyncMetrics, SyncCheckpoint
from app.utils.logger import debugLog, errorLog, infoLog

MODULE_NAME = "CrudSync"

# SyncLog CRUD Operations
def create_sync_log(
    db: Session,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    operation_type: str,
    sync_direction: str,
    status: str = "pending",
    error_message: Optional[str] = None,
    payload_checksum: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> SyncLog:
    """Erstellt einen neuen Sync-Log-Eintrag."""
    sync_log = SyncLog(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        operation_type=operation_type,
        sync_direction=sync_direction,
        status=status,
        error_message=error_message,
        payload_checksum=payload_checksum,
        metadata=metadata
    )

    try:
        db.add(sync_log)
        db.commit()
        db.refresh(sync_log)
        debugLog(MODULE_NAME, f"Created sync log entry {sync_log.id}", details={
            "tenant_id": tenant_id, "entity_type": entity_type, "entity_id": entity_id
        })
        return sync_log
    except Exception as e:
        db.rollback()
        errorLog(MODULE_NAME, f"Error creating sync log entry", details={
            "tenant_id": tenant_id, "entity_type": entity_type, "error": str(e)
        })
        raise

def update_sync_log_status(
    db: Session,
    sync_log_id: str,
    status: str,
    error_message: Optional[str] = None,
    processed_at: Optional[datetime] = None
) -> Optional[SyncLog]:
    """Aktualisiert den Status eines Sync-Log-Eintrags."""
    try:
        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        if not sync_log:
            return None

        sync_log.status = status
        if error_message:
            sync_log.error_message = error_message
        if processed_at:
            sync_log.processed_at = processed_at
        else:
            sync_log.processed_at = datetime.utcnow()

        db.commit()
        db.refresh(sync_log)
        debugLog(MODULE_NAME, f"Updated sync log {sync_log_id} status to {status}")
        return sync_log
    except Exception as e:
        db.rollback()
        errorLog(MODULE_NAME, f"Error updating sync log status", details={
            "sync_log_id": sync_log_id, "error": str(e)
        })
        raise

def get_sync_logs_by_tenant(
    db: Session,
    tenant_id: str,
    limit: int = 100,
    status: Optional[str] = None
) -> List[SyncLog]:
    """Ruft Sync-Logs für einen Mandanten ab."""
    try:
        query = db.query(SyncLog).filter(SyncLog.tenant_id == tenant_id)
        if status:
            query = query.filter(SyncLog.status == status)

        logs = query.order_by(SyncLog.created_at.desc()).limit(limit).all()
        debugLog(MODULE_NAME, f"Retrieved {len(logs)} sync logs for tenant {tenant_id}")
        return logs
    except Exception as e:
        errorLog(MODULE_NAME, f"Error retrieving sync logs", details={
            "tenant_id": tenant_id, "error": str(e)
        })
        raise

# SyncConflict CRUD Operations
def create_sync_conflict(
    db: Session,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    local_checksum: str,
    server_checksum: str,
    conflict_type: str = "data_mismatch",
    local_last_modified: Optional[datetime] = None,
    server_last_modified: Optional[datetime] = None,
    conflict_data: Optional[Dict[str, Any]] = None
) -> SyncConflict:
    """Erstellt einen neuen Sync-Konflikt-Eintrag."""
    conflict = SyncConflict(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        local_checksum=local_checksum,
        server_checksum=server_checksum,
        conflict_type=conflict_type,
        local_last_modified=local_last_modified,
        server_last_modified=server_last_modified,
        conflict_data=conflict_data
    )

    try:
        db.add(conflict)
        db.commit()
        db.refresh(conflict)
        infoLog(MODULE_NAME, f"Created sync conflict {conflict.id}", details={
            "tenant_id": tenant_id, "entity_type": entity_type, "entity_id": entity_id
        })
        return conflict
    except Exception as e:
        db.rollback()
        errorLog(MODULE_NAME, f"Error creating sync conflict", details={
            "tenant_id": tenant_id, "entity_type": entity_type, "error": str(e)
        })
        raise

def resolve_sync_conflict(
    db: Session,
    conflict_id: str,
    resolution_status: str,
    resolution_strategy: Optional[str] = None,
    resolved_by: Optional[str] = None
) -> Optional[SyncConflict]:
    """Löst einen Sync-Konflikt auf."""
    try:
        conflict = db.query(SyncConflict).filter(SyncConflict.id == conflict_id).first()
        if not conflict:
            return None

        conflict.resolution_status = resolution_status
        conflict.resolution_strategy = resolution_strategy
        conflict.resolved_by = resolved_by
        conflict.resolved_at = datetime.utcnow()

        db.commit()
        db.refresh(conflict)
        infoLog(MODULE_NAME, f"Resolved sync conflict {conflict_id} with strategy {resolution_strategy}")
        return conflict
    except Exception as e:
        db.rollback()
        errorLog(MODULE_NAME, f"Error resolving sync conflict", details={
            "conflict_id": conflict_id, "error": str(e)
        })
        raise

def get_pending_conflicts_by_tenant(db: Session, tenant_id: str) -> List[SyncConflict]:
    """Ruft ausstehende Konflikte für einen Mandanten ab."""
    try:
        conflicts = db.query(SyncConflict).filter(
            SyncConflict.tenant_id == tenant_id,
            SyncConflict.resolution_status == "pending"
        ).order_by(SyncConflict.created_at.desc()).all()

        debugLog(MODULE_NAME, f"Retrieved {len(conflicts)} pending conflicts for tenant {tenant_id}")
        return conflicts
    except Exception as e:
        errorLog(MODULE_NAME, f"Error retrieving pending conflicts", details={
            "tenant_id": tenant_id, "error": str(e)
        })
        raise

# SyncMetrics CRUD Operations
def create_sync_metrics(
    db: Session,
    tenant_id: str,
    sync_session_id: str,
    sync_type: str,
    trigger_source: Optional[str] = None
) -> SyncMetrics:
    """Erstellt einen neuen Sync-Metriken-Eintrag."""
    metrics = SyncMetrics(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        sync_session_id=sync_session_id,
        start_time=datetime.utcnow(),
        sync_type=sync_type,
        trigger_source=trigger_source
    )

    try:
        db.add(metrics)
        db.commit()
        db.refresh(metrics)
        debugLog(MODULE_NAME, f"Created sync metrics {metrics.id}", details={
            "tenant_id": tenant_id, "sync_session_id": sync_session_id
        })
        return metrics
    except Exception as e:
        db.rollback()
        errorLog(MODULE_NAME, f"Error creating sync metrics", details={
            "tenant_id": tenant_id, "error": str(e)
        })
        raise

def complete_sync_metrics(
    db: Session,
    metrics_id: str,
    success: bool,
    entities_processed: int = 0,
    entities_successful: int = 0,
    entities_failed: int = 0,
    conflicts_detected: int = 0,
    error_summary: Optional[str] = None,
    performance_data: Optional[Dict[str, Any]] = None
) -> Optional[SyncMetrics]:
    """Vervollständigt einen Sync-Metriken-Eintrag."""
    try:
        metrics = db.query(SyncMetrics).filter(SyncMetrics.id == metrics_id).first()
        if not metrics:
            return None

        end_time = datetime.utcnow()
        metrics.end_time = end_time
        metrics.duration_ms = int((end_time - metrics.start_time).total_seconds() * 1000)
        metrics.success = success
        metrics.entities_processed = entities_processed
        metrics.entities_successful = entities_successful
        metrics.entities_failed = entities_failed
        metrics.conflicts_detected = conflicts_detected
        metrics.error_summary = error_summary
        metrics.performance_data = performance_data

        db.commit()
        db.refresh(metrics)
        infoLog(MODULE_NAME, f"Completed sync metrics {metrics_id}", details={
            "duration_ms": metrics.duration_ms, "success": success, "entities_processed": entities_processed
        })
        return metrics
    except Exception as e:
        db.rollback()
        errorLog(MODULE_NAME, f"Error completing sync metrics", details={
            "metrics_id": metrics_id, "error": str(e)
        })
        raise

# SyncCheckpoint CRUD Operations
def create_sync_checkpoint(
    db: Session,
    tenant_id: str,
    checkpoint_type: str,
    entity_counts: Optional[Dict[str, int]] = None,
    data_checksums: Optional[Dict[str, str]] = None,
    sync_version: Optional[str] = None
) -> SyncCheckpoint:
    """Erstellt einen neuen Sync-Checkpoint."""
    checkpoint = SyncCheckpoint(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        checkpoint_type=checkpoint_type,
        last_sync_time=datetime.utcnow(),
        entity_counts=entity_counts,
        data_checksums=data_checksums,
        sync_version=sync_version
    )

    try:
        db.add(checkpoint)
        db.commit()
        db.refresh(checkpoint)
        infoLog(MODULE_NAME, f"Created sync checkpoint {checkpoint.id}", details={
            "tenant_id": tenant_id, "checkpoint_type": checkpoint_type
        })
        return checkpoint
    except Exception as e:
        db.rollback()
        errorLog(MODULE_NAME, f"Error creating sync checkpoint", details={
            "tenant_id": tenant_id, "error": str(e)
        })
        raise

def get_latest_checkpoint(db: Session, tenant_id: str, checkpoint_type: str) -> Optional[SyncCheckpoint]:
    """Ruft den neuesten Checkpoint für einen Mandanten ab."""
    try:
        checkpoint = db.query(SyncCheckpoint).filter(
            SyncCheckpoint.tenant_id == tenant_id,
            SyncCheckpoint.checkpoint_type == checkpoint_type,
            SyncCheckpoint.is_valid == True
        ).order_by(SyncCheckpoint.created_at.desc()).first()

        if checkpoint:
            debugLog(MODULE_NAME, f"Retrieved latest checkpoint {checkpoint.id} for tenant {tenant_id}")
        return checkpoint
    except Exception as e:
        errorLog(MODULE_NAME, f"Error retrieving latest checkpoint", details={
            "tenant_id": tenant_id, "checkpoint_type": checkpoint_type, "error": str(e)
        })
        raise
