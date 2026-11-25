from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.contacts import get_contacts

router = APIRouter(tags=["contacts"])


@router.get("/contacts")
async def public_contacts(db: AsyncSession = Depends(get_db)):
    """Публичные контакты сервиса для экрана «Контакты» клиента."""
    return {"contacts_text": await get_contacts(db)}
