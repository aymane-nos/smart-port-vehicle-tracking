from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

import crud
from database import get_session
from models import VehicleStatus
from schemas import VehicleRead, VehicleUpdate

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleRead])
async def list_vehicles(
    status: VehicleStatus | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_vehicles(session, status, limit, offset)


@router.get("/{plate_number}", response_model=VehicleRead)
async def get_vehicle(plate_number: str, session: AsyncSession = Depends(get_session)):
    vehicle = await crud.get_vehicle_by_plate(session, plate_number)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    return vehicle


@router.patch("/{plate_number}", response_model=VehicleRead)
async def update_vehicle(
    plate_number: str,
    payload: VehicleUpdate,
    session: AsyncSession = Depends(get_session),
):
    vehicle = await crud.get_vehicle_by_plate(session, plate_number)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(vehicle, field, value)

    session.add(vehicle)
    await session.commit()
    await session.refresh(vehicle)
    return vehicle
