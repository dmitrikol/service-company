from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.appointment import Appointment
from app.models.service import Service
from app.models.car import Car
from app.models.client import Client
from app.models.user import User, PlatformAccount
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone, date, time
from app.services.schedule import get_schedule, get_timezone, validate_schedule
from app.services.clients import find_client_by_phone, merge_client_into

router = APIRouter(tags=["appointments"])


def _to_utc(value: datetime, tz) -> datetime:
    """Naive — локальное время сервиса; в БД всегда пишем UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(timezone.utc)


def _local_iso(value: datetime | None, tz) -> str | None:
    """Отдаём время клиенту уже в локальной таймзоне сервиса."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz).isoformat()


@router.get("/schedule")
async def public_schedule(db: AsyncSession = Depends(get_db)):
    """Публичное расписание работы сервиса (для подсказки клиенту)."""
    return await get_schedule(db)

@router.get("/appointments/slots")
async def get_busy_slots(
    date_param: date = Query(..., alias="date"),
    service_id: int = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Занятые интервалы дня — для подсветки занятых слотов в календаре бота.

    Если задан service_id — учитываются только записи услуг того же типа, что и
    выбранная (PDR не пересекается с обычными услугами и наоборот). Без
    service_id возвращаются все занятые интервалы (обратная совместимость).
    """
    # Дата из календаря — локальная для сервиса; границы дня ищем в UTC.
    tz = get_timezone(await get_schedule(db))
    start_of_day = datetime.combine(date_param, time.min, tzinfo=tz).astimezone(timezone.utc)
    end_of_day = datetime.combine(date_param, time.max, tzinfo=tz).astimezone(timezone.utc)
    stmt = select(Appointment).join(Appointment.service).where(
        Appointment.status != "cancelled",
        Appointment.start_datetime < end_of_day,
        Appointment.end_datetime > start_of_day,
    )
    if service_id is not None:
        service = await db.get(Service, service_id)
        if service:
            stmt = stmt.where(Service.is_pdr == service.is_pdr)
    apps = (await db.execute(stmt)).scalars().all()
    return [
        {"start": _local_iso(a.start_datetime, tz), "end": _local_iso(a.end_datetime, tz)}
        for a in apps
    ]

@router.get("/appointments/my")
async def get_my_appointments(
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    user = await _get_user(db, platform, user_id)
    client = (await db.execute(select(Client).where(Client.user_id == user.id))).scalars().first()
    if not client:
        return []
    tz = get_timezone(await get_schedule(db))
    stmt = select(Appointment).options(
        selectinload(Appointment.car),
        selectinload(Appointment.service)
    ).where(Appointment.client_id == client.id).order_by(Appointment.start_datetime.desc())
    apps = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": a.id,
            "car": f"{a.car.brand} {a.car.model}",
            "service": a.service.name,
            "service_id": a.service_id,
            "duration_minutes": a.service.duration_minutes,
            "start": _local_iso(a.start_datetime, tz),
            "end": _local_iso(a.end_datetime, tz),
            "status": a.status
        }
        for a in apps
    ]

@router.post("/appointments")
async def create_appointment(
    car_id: int,
    service_id: int,
    start_datetime: datetime,
    phone: str = None,
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    user = await _get_user(db, platform, user_id)
    client = (await db.execute(select(Client).where(Client.user_id == user.id))).scalars().first()
    if not client:
        raise HTTPException(status_code=400, detail="No client profile")
    # Телефон клиент вводит один раз при записи — сохраняем на профиль,
    # чтобы он был в карточке работы
    if phone and phone.strip():
        phone = phone.strip()
        # Тот же человек на другой платформе: поднимаем его карточку по номеру
        # телефона и переносим аккаунты/машины/записи к ней
        matched = await find_client_by_phone(db, phone)
        if matched and matched.id != client.id:
            await merge_client_into(db, from_client=client, to_client=matched)
            client = matched
        client.phone = phone

    # Машина должна принадлежать текущему клиенту — иначе можно было бы
    # записаться на чужой car_id, просто подобрав число
    car = (await db.execute(
        select(Car).where(Car.id == car_id, Car.client_id == client.id, Car.is_active.is_(True))
    )).scalars().first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    service = (await db.execute(select(Service).where(Service.id == service_id))).scalars().first()
    if not service or not service.is_active:
        raise HTTPException(status_code=400, detail="Service not available")

    # Проверка по рабочему расписанию (часы, рабочие дни, выходные даты)
    schedule = await get_schedule(db)
    tz = get_timezone(schedule)
    start_datetime = _to_utc(start_datetime, tz)
    end_datetime = start_datetime + timedelta(minutes=service.duration_minutes)
    error = validate_schedule(start_datetime, end_datetime, schedule)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # Проверка на пересечение с записями того же типа (PDR не пересекается с
    # обычными услугами и наоборот — у PDR свой учёт времени)
    conflict_stmt = select(Appointment).join(Appointment.service).where(
        Appointment.status != "cancelled",
        Appointment.start_datetime < end_datetime,
        Appointment.end_datetime > start_datetime,
        Service.is_pdr == service.is_pdr,
    )
    conflicts = (await db.execute(conflict_stmt)).scalars().all()
    if conflicts:
        raise HTTPException(status_code=409, detail="Time slot is already taken")

    appointment = Appointment(
        client_id=client.id,
        car_id=car_id,
        service_id=service_id,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        status="booked"
    )
    db.add(appointment)
    await db.commit()
    return {"id": appointment.id, "message": "Appointment created"}

@router.post("/appointments/{appointment_id}/cancel")
async def cancel_my_appointment(
    appointment_id: int,
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Отмена клиентом своей записи (только пока она ещё не началась)."""
    user = await _get_user(db, platform, user_id)
    client = (await db.execute(select(Client).where(Client.user_id == user.id))).scalars().first()
    if not client:
        raise HTTPException(status_code=400, detail="No client profile")

    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.client_id != client.id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    if appointment.status != "booked":
        raise HTTPException(status_code=400, detail="Appointment is not cancellable")

    start = appointment.start_datetime
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if start <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Appointment already started")

    appointment.status = "cancelled"
    appointment.cancelled_by = "client"
    await db.commit()
    return {"id": appointment.id, "status": "cancelled"}

@router.post("/appointments/{appointment_id}/reschedule")
async def reschedule_my_appointment(
    appointment_id: int,
    start_datetime: datetime,
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Перенос своей записи на другое время (вместо отмены + записи заново)."""
    user = await _get_user(db, platform, user_id)
    client = (await db.execute(select(Client).where(Client.user_id == user.id))).scalars().first()
    if not client:
        raise HTTPException(status_code=400, detail="No client profile")

    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.client_id != client.id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    if appointment.status != "booked":
        raise HTTPException(status_code=400, detail="Appointment is not reschedulable")

    old_start = appointment.start_datetime
    if old_start.tzinfo is None:
        old_start = old_start.replace(tzinfo=timezone.utc)
    if old_start <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Appointment already started")

    service = await db.get(Service, appointment.service_id)
    if not service:
        raise HTTPException(status_code=400, detail="Service not found")
    schedule = await get_schedule(db)
    tz = get_timezone(schedule)
    start_datetime = _to_utc(start_datetime, tz)
    end_datetime = start_datetime + timedelta(minutes=service.duration_minutes)
    error = validate_schedule(start_datetime, end_datetime, schedule)
    if error:
        raise HTTPException(status_code=400, detail=error)

    conflict_stmt = select(Appointment).join(Appointment.service).where(
        Appointment.id != appointment.id,
        Appointment.status != "cancelled",
        Appointment.start_datetime < end_datetime,
        Appointment.end_datetime > start_datetime,
        Service.is_pdr == service.is_pdr,
    )
    conflicts = (await db.execute(conflict_stmt)).scalars().all()
    if conflicts:
        raise HTTPException(status_code=409, detail="Time slot is already taken")

    appointment.start_datetime = start_datetime
    appointment.end_datetime = end_datetime
    # Новое время — старые напоминания больше не актуальны, шлём заново
    appointment.reminded_at = None
    appointment.reminded_soon_at = None
    await db.commit()
    return {"id": appointment.id, "start": _local_iso(appointment.start_datetime, tz),
            "end": _local_iso(appointment.end_datetime, tz), "message": "Rescheduled"}


@router.get("/works/my")
async def get_my_works(
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """История выполненных работ клиента — «мини-история обслуживания»."""
    from app.models.completed_work import CompletedWork

    user = await _get_user(db, platform, user_id)
    client = (await db.execute(select(Client).where(Client.user_id == user.id))).scalars().first()
    if not client:
        return []
    tz = get_timezone(await get_schedule(db))
    stmt = select(CompletedWork).options(
        selectinload(CompletedWork.car),
        selectinload(CompletedWork.service),
    ).where(CompletedWork.client_id == client.id).order_by(CompletedWork.performed_at.desc())
    works = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": w.id,
            "car": f"{w.car.brand} {w.car.model}" if w.car else "—",
            "service": w.service.name if w.service else "—",
            "actual_price": w.actual_price,
            "total_amount": w.total_amount,
            "performed_at": _local_iso(w.performed_at, tz),
        }
        for w in works
    ]


async def _get_user(db, platform, external_id):
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