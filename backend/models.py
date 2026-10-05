"""
Modèles ORM (SQLModel = Pydantic + SQLAlchemy).
Indexation : plate_number (unique) et timestamp pour requêtes temporelles
rapides sur les détections (dashboard temps réel + analytics).
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class VehicleStatus(str, Enum):
    IN_PORT = "IN_PORT"
    OUT = "OUT"
    UNKNOWN = "UNKNOWN"


class VehicleType(str, Enum):
    CAR = "CAR"
    TRUCK = "TRUCK"
    CONTAINER_TRUCK = "CONTAINER_TRUCK"
    BUS = "BUS"
    MOTORCYCLE = "MOTORCYCLE"
    OTHER = "OTHER"


class Direction(str, Enum):
    IN = "IN"
    OUT = "OUT"


class VehicleBase(SQLModel):
    plate_number: str = Field(index=True, unique=True, max_length=20)
    vehicle_type: VehicleType = Field(default=VehicleType.OTHER)
    status: VehicleStatus = Field(default=VehicleStatus.UNKNOWN, index=True)
    is_authorized: bool = Field(default=True)
    notes: Optional[str] = None


class Vehicle(VehicleBase, table=True):
    __tablename__ = "vehicles"

    id: Optional[int] = Field(default=None, primary_key=True)
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    detections: list["Detection"] = Relationship(back_populates="vehicle")


class DetectionBase(SQLModel):
    plate_raw: str = Field(max_length=20, index=True)
    plate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    detection_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    gate_id: str = Field(index=True, max_length=50)
    direction: Direction = Field(default=Direction.IN)
    vehicle_type: VehicleType = Field(default=VehicleType.OTHER)
    track_id: Optional[int] = Field(default=None, index=True)
    image_path: Optional[str] = None


class Detection(DetectionBase, table=True):
    __tablename__ = "detections"

    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicles.id", index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)

    vehicle: Optional[Vehicle] = Relationship(back_populates="detections")


class DailyTrafficSummary(SQLModel, table=True):
    """
    Table de faits agrégée (mini-datawarehouse) : une ligne par
    (jour, porte, type de véhicule), produite par le job ETL batch
    (voir etl/aggregate_daily_traffic.py) à partir des `detections` brutes.
    Contrainte d'unicité = clé de la partition rechargée à chaque run,
    ce qui rend le job idempotent (relancer le même jour ne duplique rien).
    """

    __tablename__ = "daily_traffic_summary"
    __table_args__ = (
        UniqueConstraint(
            "summary_date", "gate_id", "vehicle_type", name="uq_daily_summary_partition"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    summary_date: date = Field(index=True)
    gate_id: str = Field(index=True, max_length=50)
    vehicle_type: VehicleType
    entries_count: int = Field(default=0)
    exits_count: int = Field(default=0)
    unique_vehicles_count: int = Field(default=0)
    avg_plate_confidence: float = Field(default=0.0)
    computed_at: datetime = Field(default_factory=datetime.utcnow)
