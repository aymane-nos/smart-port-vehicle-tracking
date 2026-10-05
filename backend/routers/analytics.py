from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

import crud
from database import get_session
from schemas import AlertItem, DailyTrafficSummaryRead, PortOccupancy, TrafficPoint

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/occupancy", response_model=PortOccupancy)
async def occupancy(session: AsyncSession = Depends(get_session)):
    """Nombre de véhicules actuellement dans le port, par type."""
    return await crud.get_port_occupancy(session)


@router.get("/traffic", response_model=list[TrafficPoint])
async def traffic(
    hours: int = Query(24, ge=1, le=168),
    session: AsyncSession = Depends(get_session),
):
    """Entrées/sorties agrégées par heure sur les N dernières heures."""
    return await crud.get_traffic_timeseries(session, hours)


@router.get("/alerts", response_model=list[AlertItem])
async def alerts(
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Véhicules non autorisés / lectures OCR peu fiables, les plus récentes."""
    return await crud.get_alerts(session, limit)


@router.get("/daily-summary", response_model=list[DailyTrafficSummaryRead])
async def daily_summary(
    days: int = Query(14, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    """
    Table de faits agrégée (jour x porte x type de véhicule), produite par
    le job ETL batch (voir backend/etl/aggregate_daily_traffic.py), exécuté
    automatiquement chaque jour à 01:00 UTC.
    """
    return await crud.get_daily_summary(session, days)
