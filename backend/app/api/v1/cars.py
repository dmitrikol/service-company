from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.car import Car
from app.models.client import Client
from app.models.user import User, PlatformAccount
from sqlalchemy import select

router = APIRouter(tags=["cars"])

def _car_dict(c: Car) -> dict:
    return {
        "id": c.id,
        "brand": c.brand,
        "model": c.model,
        "plate_number": c.plate_number,
        "vin": c.vin,
        "comment": c.comment,
    }

@router.get("/cars")
async def get_my_cars(
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    # Находим user по платформе
    user = await _get_user_by_platform(db, platform, user_id)
    client_stmt = select(Client).where(Client.user_id == user.id)
    client = (await db.execute(client_stmt)).scalars().first()
    if not client:
        return []
    cars_stmt = select(Car).where(Car.client_id == client.id, Car.is_active.is_(True))
    cars = (await db.execute(cars_stmt)).scalars().all()
    return [_car_dict(c) for c in cars]

@router.post("/cars")
async def add_car(
    brand: str,
    model: str,
    plate_number: str = None,
    vin: str = None,
    comment: str = None,
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    user = await _get_user_by_platform(db, platform, user_id)
    client_stmt = select(Client).where(Client.user_id == user.id)
    client = (await db.execute(client_stmt)).scalars().first()
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found. Register with phone first.")
    car = Car(
        client_id=client.id,
        brand=brand,
        model=model,
        plate_number=plate_number,
        vin=vin,
        comment=comment
    )
    db.add(car)
    await db.commit()
    return {"id": car.id, "message": "Car added"}


async def _get_own_car(db, platform, user_id, car_id) -> Car:
    """Машина клиента, отправившего запрос — с проверкой владения (404, если чужая)."""
    user = await _get_user_by_platform(db, platform, user_id)
    client = (await db.execute(
        select(Client).where(Client.user_id == user.id)
    )).scalars().first()
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found")
    car = (await db.execute(
        select(Car).where(Car.id == car_id, Car.client_id == client.id, Car.is_active.is_(True))
    )).scalars().first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    return car


@router.patch("/cars/{car_id}")
async def update_car(
    car_id: int,
    brand: str = None,
    model: str = None,
    plate_number: str = None,
    vin: str = None,
    comment: str = None,
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Редактирование своей машины (например, исправить опечатку в номере/VIN)."""
    car = await _get_own_car(db, platform, user_id, car_id)
    if brand is not None:
        car.brand = brand
    if model is not None:
        car.model = model
    if plate_number is not None:
        car.plate_number = plate_number or None
    if vin is not None:
        car.vin = vin or None
    if comment is not None:
        car.comment = comment or None
    await db.commit()
    await db.refresh(car)
    return _car_dict(car)


@router.delete("/cars/{car_id}")
async def delete_car(
    car_id: int,
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Мягкое удаление своей машины: скрывает из списка, история записей сохраняется."""
    car = await _get_own_car(db, platform, user_id, car_id)
    car.is_active = False
    await db.commit()
    return {"id": car.id, "is_active": car.is_active}


async def _get_user_by_platform(db, platform, external_id):
    stmt = select(PlatformAccount).where(
        PlatformAccount.platform == platform,
        PlatformAccount.external_id == external_id
    )
    result = await db.execute(stmt)
    pa = result.scalars().first()
    if not pa:
        raise HTTPException(status_code=404, detail="User not registered")
    # Явная async-загрузка user, чтобы избежать lazy-load (MissingGreenlet)
    return await db.get(User, pa.user_id)