"""Tests du job ETL (etl/aggregate_daily_traffic.py) — agrégation + idempotence."""
from datetime import date, datetime

from sqlalchemy import select

from etl.aggregate_daily_traffic import run_etl
from models import DailyTrafficSummary, Detection, Direction, Vehicle, VehicleType


async def test_etl_aggregates_entries_exits_and_unique_vehicles(db_session):
    vehicle = Vehicle(plate_number="ETLTEST", vehicle_type=VehicleType.CAR)
    db_session.add(vehicle)
    await db_session.flush()

    target_date = date(2026, 1, 15)
    ts = datetime(2026, 1, 15, 9, 0, 0)
    db_session.add(Detection(
        plate_raw="ETLTEST", plate_confidence=0.9, detection_confidence=0.9,
        gate_id="G1", direction=Direction.IN, vehicle_type=VehicleType.CAR,
        vehicle_id=vehicle.id, timestamp=ts,
    ))
    db_session.add(Detection(
        plate_raw="ETLTEST", plate_confidence=0.7, detection_confidence=0.9,
        gate_id="G1", direction=Direction.OUT, vehicle_type=VehicleType.CAR,
        vehicle_id=vehicle.id, timestamp=ts.replace(hour=15),
    ))
    await db_session.commit()

    n_written = await run_etl(target_date=target_date)
    assert n_written == 1  # une seule partition (G1, CAR) ce jour-là

    result = await db_session.execute(
        select(DailyTrafficSummary).where(DailyTrafficSummary.summary_date == target_date)
    )
    row = result.scalar_one()
    assert row.gate_id == "G1"
    assert row.entries_count == 1
    assert row.exits_count == 1
    assert row.unique_vehicles_count == 1
    assert row.avg_plate_confidence == 0.8  # moyenne de 0.9 et 0.7


async def test_etl_is_idempotent_on_rerun(db_session):
    """Relancer le job sur la même date ne doit JAMAIS dupliquer les lignes."""
    target_date = date(2026, 2, 1)
    db_session.add(Detection(
        plate_raw="IDEMPO1", plate_confidence=0.9, detection_confidence=0.9,
        gate_id="G1", direction=Direction.IN, vehicle_type=VehicleType.CAR,
        timestamp=datetime(2026, 2, 1, 10, 0, 0),
    ))
    await db_session.commit()

    await run_etl(target_date=target_date)
    await run_etl(target_date=target_date)
    await run_etl(target_date=target_date)

    result = await db_session.execute(
        select(DailyTrafficSummary).where(DailyTrafficSummary.summary_date == target_date)
    )
    rows = result.scalars().all()
    assert len(rows) == 1  # pas de doublon après 3 exécutions


async def test_etl_ignores_detections_outside_target_date(db_session):
    db_session.add(Detection(
        plate_raw="WRONGDAY", plate_confidence=0.9, detection_confidence=0.9,
        gate_id="G1", direction=Direction.IN, vehicle_type=VehicleType.CAR,
        timestamp=datetime(2026, 3, 1, 10, 0, 0),
    ))
    await db_session.commit()

    n_written = await run_etl(target_date=date(2026, 3, 2))  # un autre jour
    assert n_written == 0
