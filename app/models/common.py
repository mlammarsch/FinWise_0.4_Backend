from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

class TimeStampedModel(BaseModel):
    # Diese Klasse dient als Basis für Pydantic-Modelle, die Zeitstempel benötigen,
    # aber nicht direkt SQLModel-Tabellen repräsentieren.
    # SQLModel-Tabellen definieren ihre Felder direkt.
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # tenant_id: UUID # Sollte im spezifischen DB-Modell als ForeignKey definiert sein
