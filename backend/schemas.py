"""
Schémas Pydantic v2 exposés par l'API — découplés des modèles ORM (models.py)
pour ne jamais fuiter de détails internes et pour permettre une évolution
indépendante du contrat API / du schéma BDD.
"""
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models import Direction, VehicleStatus, VehicleType


# ---------- Vehicle ----------
class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_number: str
    vehicle_type: VehicleType
    status: VehicleStatus
    is_authorized: bool
    first_seen_at: datetime
    last_seen_at: datetime


class VehicleUpdate(BaseModel):
    is_authorized: Optional[bool] = None
    notes: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None


# ---------- Detection ----------
class DetectionCreate(BaseModel):
    """Payload envoyé par ai_service à chaque détection consolidée."""

    plate_raw: str = Field(..., min_length=2, max_length=20)
    plate_confidence: float = Field(..., ge=0.0, le=1.0)
    detection_confidence: float = Field(..., ge=0.0, le=1.0)
    gate_id: str = Field(..., max_length=50)
    direction: Direction = Direction.IN
    vehicle_type: VehicleType = VehicleType.OTHER
    track_id: Optional[int] = None
    image_path: Optional[str] = None
    timestamp: Optional[datetime] = None

    @field_validator("timestamp")
    @classmethod
    def _normalize_to_naive_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        """
        Les colonnes BDD stockent des TIMESTAMP WITHOUT TIME ZONE. ai_service
        envoie un timestamp timezone-aware (ISO 8601 avec offset) — on le
        convertit ici en UTC naïf pour rester compatible avec asyncpg, qui
        refuse de mélanger datetime naïf/aware dans une même requête.
        """
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class DetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_raw: str
    plate_confidence: float
    detection_confidence: float
    gate_id: str
    direction: Direction
    vehicle_type: VehicleType
    track_id: Optional[int]
    image_path: Optional[str]
    timestamp: datetime
    vehicle_id: Optional[int]


# ---------- Analytics ----------
class PortOccupancy(BaseModel):
    total_in_port: int
    by_vehicle_type: dict[str, int]
    last_updated: datetime


class TrafficPoint(BaseModel):
    period: str  # ex: "2026-09-02T14:00:00"
    entries: int
    exits: int


class AlertItem(BaseModel):
    type: str  # "UNAUTHORIZED_VEHICLE" | "LOW_CONFIDENCE_OCR"
    message: str
    detection_id: int
    plate: str
    timestamp: datetime


class DailyTrafficSummaryRead(BaseModel):
    """Une ligne de la table de faits produite par le job ETL (etl/)."""

    model_config = ConfigDict(from_attributes=True)

    summary_date: date
    gate_id: str
    vehicle_type: VehicleType
    entries_count: int
    exits_count: int
    unique_vehicles_count: int
    avg_plate_confidence: float
    computed_at: datetime
