"""
Couche d'accès aux données. Toute la logique métier de persistance vit ici,
séparée des routers (HTTP) et des schémas (contrat API).
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DailyTrafficSummary, Detection, Direction, Vehicle, VehicleStatus
from schemas import DetectionCreate


async def get_or_create_vehicle(
    session: AsyncSession, plate_number: str, vehicle_type
) -> Vehicle:
    result = await session.execute(
        select(Vehicle).where(Vehicle.plate_number == plate_number)
    )
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        vehicle = Vehicle(plate_number=plate_number, vehicle_type=vehicle_type)
        session.add(vehicle)
        await session.flush()  # obtenir vehicle.id sans commit
    return vehicle


async def create_detection(session: AsyncSession, payload: DetectionCreate) -> Detection:
    """
    Enregistre une détection consolidée, upsert le véhicule associé (par
    plaque) et met à jour son statut courant (IN_PORT / OUT) selon la
    direction franchie.
    """
    vehicle = await get_or_create_vehicle(session, payload.plate_raw, payload.vehicle_type)

    now = payload.timestamp or datetime.utcnow()
    vehicle.last_seen_at = now
    vehicle.status = (
        VehicleStatus.IN_PORT if payload.direction == Direction.IN else VehicleStatus.OUT
    )

    detection = Detection(
        **payload.model_dump(exclude={"timestamp"}),
        timestamp=now,
        vehicle_id=vehicle.id,
    )
    session.add(detection)
    await session.commit()
    await session.refresh(detection)
    return detection


async def list_detections(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    plate: str | None = None,
    gate_id: str | None = None,
) -> list[Detection]:
    query = select(Detection).order_by(Detection.timestamp.desc())
    if plate:
        query = query.where(Detection.plate_raw.ilike(f"%{plate}%"))
    if gate_id:
        query = query.where(Detection.gate_id == gate_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_vehicles(
    session: AsyncSession,
    status: VehicleStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Vehicle]:
    query = select(Vehicle).order_by(Vehicle.last_seen_at.desc())
    if status:
        query = query.where(Vehicle.status == status)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_vehicle_by_plate(session: AsyncSession, plate_number: str) -> Vehicle | None:
    result = await session.execute(
        select(Vehicle).where(Vehicle.plate_number == plate_number)
    )
    return result.scalar_one_or_none()


# ---------- Analytics ----------
async def get_port_occupancy(session: AsyncSession) -> dict:
    total_query = select(func.count()).select_from(Vehicle).where(
        Vehicle.status == VehicleStatus.IN_PORT
    )
    total = (await session.execute(total_query)).scalar_one()

    by_type_query = (
        select(Vehicle.vehicle_type, func.count())
        .where(Vehicle.status == VehicleStatus.IN_PORT)
        .group_by(Vehicle.vehicle_type)
    )
    by_type_rows = (await session.execute(by_type_query)).all()

    return {
        "total_in_port": total,
        "by_vehicle_type": {vt.value: count for vt, count in by_type_rows},
        "last_updated": datetime.utcnow(),
    }


async def get_traffic_timeseries(session: AsyncSession, hours: int = 24) -> list[dict]:
    """Agrège entrées/sorties par tranche horaire sur les N dernières heures."""
    since = datetime.utcnow() - timedelta(hours=hours)
    bucket = func.date_trunc("hour", Detection.timestamp)

    query = (
        select(
            bucket.label("period"),
            Detection.direction,
            func.count().label("count"),
        )
        .where(Detection.timestamp >= since)
        .group_by(bucket, Detection.direction)
        .order_by(bucket)
    )
    rows = (await session.execute(query)).all()

    aggregated: dict[str, dict[str, int]] = {}
    for period, direction, count in rows:
        key = period.isoformat()
        aggregated.setdefault(key, {"entries": 0, "exits": 0})
        if direction == Direction.IN:
            aggregated[key]["entries"] = count
        else:
            aggregated[key]["exits"] = count

    return [
        {"period": period, "entries": v["entries"], "exits": v["exits"]}
        for period, v in sorted(aggregated.items())
    ]


async def get_alerts(session: AsyncSession, limit: int = 20) -> list[dict]:
    """
    Alertes simples : détections liées à des véhicules non autorisés, ou
    lectures OCR à faible confiance (à vérifier manuellement).
    """
    query = (
        select(Detection, Vehicle)
        .join(Vehicle, Detection.vehicle_id == Vehicle.id)
        .where((Vehicle.is_authorized == False) | (Detection.plate_confidence < 0.5))  # noqa: E712
        .order_by(Detection.timestamp.desc())
        .limit(limit)
    )
    rows = (await session.execute(query)).all()

    alerts = []
    for detection, vehicle in rows:
        if not vehicle.is_authorized:
            alert_type, message = "UNAUTHORIZED_VEHICLE", "Véhicule non autorisé détecté"
        else:
            alert_type, message = "LOW_CONFIDENCE_OCR", "Lecture de plaque peu fiable"
        alerts.append(
            {
                "type": alert_type,
                "message": message,
                "detection_id": detection.id,
                "plate": detection.plate_raw,
                "timestamp": detection.timestamp,
            }
        )
    return alerts


async def get_daily_summary(session: AsyncSession, days: int = 14) -> list[DailyTrafficSummary]:
    """Lit la table de faits produite par le job ETL (etl/aggregate_daily_traffic.py)."""
    since = datetime.utcnow().date() - timedelta(days=days)
    query = (
        select(DailyTrafficSummary)
        .where(DailyTrafficSummary.summary_date >= since)
        .order_by(DailyTrafficSummary.summary_date.desc(), DailyTrafficSummary.gate_id)
    )
    result = await session.execute(query)
    return list(result.scalars().all())
