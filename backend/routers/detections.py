from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

import crud
from database import get_session
from schemas import DetectionCreate, DetectionRead

router = APIRouter(prefix="/detections", tags=["detections"])


@router.post("", response_model=DetectionRead, status_code=201)
async def create_detection(
    payload: DetectionCreate,
    session: AsyncSession = Depends(get_session),
):
    """
    Endpoint appelé par `ai_service` pour chaque détection consolidée
    (une plaque, une fois par passage, après tracking anti-doublon).
    """
    detection = await crud.create_detection(session, payload)
    return detection


@router.get("", response_model=list[DetectionRead])
async def list_detections(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    plate: str | None = None,
    gate_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await crud.list_detections(session, limit, offset, plate, gate_id)
