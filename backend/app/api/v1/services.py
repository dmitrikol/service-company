from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.service import Service
from sqlalchemy import select

router = APIRouter(tags=["services"])

@router.get("/services")
async def get_services(db: AsyncSession = Depends(get_db)):
    stmt = select(Service).where(Service.is_active == True).order_by(Service.id)
    result = await db.execute(stmt)
    services = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "price_from": s.price_from,
            "duration_minutes": s.duration_minutes,
            "is_pdr": s.is_pdr,
        }
        for s in services
    ]