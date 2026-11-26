import hmac
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from minio import Minio
from app.core.config import settings
from app.core.database import get_db
from app.models.client import Client
from app.models.user import PlatformAccount
from app.models.service import Service, ServicePriceHistory
from app.models.appointment import Appointment
from app.models.completed_work import CompletedWork
from app.models.setting import Setting
from app.services.schedule import get_schedule, get_timezone
from app.services.contacts import get_contacts, CONTACTS_KEY
from app.services.works_export import build_works_xlsx

minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=False,
)
BUCKET_NAME = settings.MINIO_BUCKET_NAME


def _local_iso(value: datetime | None, tz) -> str | None:
    """Дата/время для админки — в таймзоне сервиса, а не в UTC контейнера."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz).isoformat()


router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(
    admin_secret: str | None = Header(None, alias="x-admin-secret"),
):
    """Защита админ-эндпоинтов: заголовок ``x-admin-secret`` равен HMAC_SECRET."""
    if (
        admin_secret
        and settings.HMAC_SECRET
        and hmac.compare_digest(admin_secret, settings.HMAC_SECRET)
    ):
        return
    raise HTTPException(status_code=403, detail="Forbidden")


class ServiceCreate(BaseModel):
    name: str
    description: str = None
    price_from: float
    duration_minutes: int
    is_active: bool = True
    is_pdr: bool = False


class ServiceUpdate(BaseModel):
    name: str = None
    description: str = None
    price_from: float = None
    duration_minutes: int = None
    is_active: bool = None
    is_pdr: bool = None


class AppointmentUpdate(BaseModel):
    status: str = None
    actual_price: float = None  # фактическая цена за работу (при завершении)


# ─── Клиенты ───
class ClientCreate(BaseModel):
    name: str
    phone: str = None


class ClientUpdate(BaseModel):
    name: str = None
    phone: str = None


async def _client_dict(c: Client, db) -> dict:
    """Клиент как dict для списка/карточки: VK-аккаунт + число записей."""
    vk = None
    if c.user_id:
        vk = (await db.execute(
            select(PlatformAccount).where(
                PlatformAccount.user_id == c.user_id,
                PlatformAccount.platform == "vk",
            )
        )).scalars().first()
    apps_count = (await db.execute(
        select(func.count()).select_from(Appointment).where(Appointment.client_id == c.id)
    )).scalar()
    tz = get_timezone(await get_schedule(db))
    return {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "vk_external_id": vk.external_id if vk else None,
        "vk_username": vk.username if vk else None,
        "appointments_count": apps_count,
        "created_at": _local_iso(c.created_at, tz),
    }


@router.get("/clients", dependencies=[Depends(require_admin)])
async def admin_clients(q: str = None, db: AsyncSession = Depends(get_db)):
    """Список клиентов. `q` — поиск по имени, телефону или нику VK (подстрока)."""
    clients = (await db.execute(
        select(Client).where(Client.is_active.is_(True)).order_by(Client.created_at.desc())
    )).scalars().all()
    result = [await _client_dict(c, db) for c in clients]
    if q and q.strip():
        needle = q.strip().lower()
        result = [
            c for c in result
            if needle in (c["name"] or "").lower()
            or needle in (c["phone"] or "").lower()
            or needle in (c["vk_username"] or "").lower()
        ]
    return result


@router.post("/clients", dependencies=[Depends(require_admin)])
async def admin_create_client(payload: ClientCreate, db: AsyncSession = Depends(get_db)):
    """Клиент, добавленный мастером вручную: без VK-аккаунта."""
    client = Client(name=payload.name, phone=payload.phone, is_active=True)
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return await _client_dict(client, db)


@router.patch("/clients/{client_id}", dependencies=[Depends(require_admin)])
async def admin_update_client(client_id: int, payload: ClientUpdate, db: AsyncSession = Depends(get_db)):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update")
    for key, value in fields.items():
        setattr(client, key, value)
    await db.commit()
    await db.refresh(client)
    return await _client_dict(client, db)


@router.delete("/clients/{client_id}", dependencies=[Depends(require_admin)])
async def admin_delete_client(client_id: int, db: AsyncSession = Depends(get_db)):
    """Мягкое удаление: скрывает клиента из списка, история сохраняется."""
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.is_active = False
    await db.commit()
    return {"id": client.id, "is_active": client.is_active}


class ClientMerge(BaseModel):
    from_id: int  # чей профиль удаляем (переносим всё с него)
    to_id: int    # в чью карточку переносим


@router.post("/clients/merge", dependencies=[Depends(require_admin)])
async def admin_merge_clients(payload: ClientMerge, db: AsyncSession = Depends(get_db)):
    """Слить дубли карточек вручную (на случай, если автосклейка по телефону
    не сработала — например, дубль создан руками мастера)."""
    from app.services.clients import merge_client_into

    if payload.from_id == payload.to_id:
        raise HTTPException(status_code=400, detail="Cannot merge a client into itself")
    from_client = await db.get(Client, payload.from_id)
    to_client = await db.get(Client, payload.to_id)
    if not from_client or not to_client:
        raise HTTPException(status_code=404, detail="Client not found")
    await merge_client_into(db, from_client=from_client, to_client=to_client)
    await db.refresh(to_client)
    return await _client_dict(to_client, db)


@router.get("/clients/export", dependencies=[Depends(require_admin)])
async def admin_clients_export(db: AsyncSession = Depends(get_db)):
    """Выгрузка базы клиентов и их машин в .xlsx — для бэкапа/миграции."""
    from app.models.car import Car
    from app.services.clients_export import build_clients_xlsx

    clients = (await db.execute(
        select(Client).where(Client.is_active.is_(True)).order_by(Client.created_at.desc())
    )).scalars().all()
    client_rows = [await _client_dict(c, db) for c in clients]

    cars = (await db.execute(
        select(Car).where(Car.is_active.is_(True)).order_by(Car.client_id)
    )).scalars().all()
    client_names = {c["id"]: c["name"] for c in client_rows}
    car_rows = [
        {
            "client_name": client_names.get(car.client_id, "—"),
            "brand": car.brand,
            "model": car.model,
            "plate_number": car.plate_number,
            "vin": car.vin,
        }
        for car in cars
    ]

    data = build_clients_xlsx(client_rows, car_rows)
    fname = f"клиенты_{date.today().isoformat()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


# ─── Услуги ───
@router.get("/services", dependencies=[Depends(require_admin)])
async def admin_services(db: AsyncSession = Depends(get_db)):
    services = (await db.execute(select(Service).order_by(Service.id))).scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "price_from": s.price_from,
            "duration_minutes": s.duration_minutes,
            "is_active": s.is_active,
            "is_pdr": s.is_pdr,
        }
        for s in services
    ]


@router.post("/services", dependencies=[Depends(require_admin)])
async def admin_create_service(payload: ServiceCreate, db: AsyncSession = Depends(get_db)):
    service = Service(
        name=payload.name,
        description=payload.description,
        price_from=payload.price_from,
        duration_minutes=payload.duration_minutes,
        is_active=payload.is_active,
        is_pdr=payload.is_pdr,
    )
    db.add(service)
    await db.flush()

    # Фиксируем стартовую цену в истории
    db.add(ServicePriceHistory(service_id=service.id, price_from=service.price_from))
    await db.commit()
    await db.refresh(service)
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "price_from": service.price_from,
        "duration_minutes": service.duration_minutes,
        "is_active": service.is_active,
        "is_pdr": service.is_pdr,
    }


@router.patch("/services/{service_id}", dependencies=[Depends(require_admin)])
async def admin_update_service(service_id: int, payload: ServiceUpdate, db: AsyncSession = Depends(get_db)):
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update")

    price_changed = "price_from" in fields and fields["price_from"] != service.price_from
    for key, value in fields.items():
        setattr(service, key, value)

    if price_changed:
        db.add(ServicePriceHistory(service_id=service.id, price_from=service.price_from))

    await db.commit()
    await db.refresh(service)
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "price_from": service.price_from,
        "duration_minutes": service.duration_minutes,
        "is_active": service.is_active,
        "is_pdr": service.is_pdr,
    }


@router.get("/services/{service_id}/price-history", dependencies=[Depends(require_admin)])
async def admin_service_price_history(service_id: int, db: AsyncSession = Depends(get_db)):
    """История изменения цены «от» услуги: свежие записи первыми."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    rows = (await db.execute(
        select(ServicePriceHistory)
        .where(ServicePriceHistory.service_id == service_id)
        .order_by(ServicePriceHistory.changed_at.desc(), ServicePriceHistory.id.desc())
    )).scalars().all()
    tz = get_timezone(await get_schedule(db))
    return {
        "service_id": service.id,
        "current_price": service.price_from,
        "created_at": _local_iso(service.created_at, tz),
        "history": [
            {"price_from": r.price_from,
             "changed_at": _local_iso(r.changed_at, tz)}
            for r in rows
        ],
    }


@router.get("/services/{service_id}/export", dependencies=[Depends(require_admin)])
async def admin_service_export(service_id: int, db: AsyncSession = Depends(get_db)):
    """Выгрузка по одной услуге в .xlsx: кто и когда заплатил какую цену +
    история изменения базовой цены «от». Работает для любой услуги —
    активной, скрытой, старой или только что добавленной."""
    from app.services.service_export import build_service_export_xlsx

    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    works_stmt = select(CompletedWork).options(
        selectinload(CompletedWork.client),
        selectinload(CompletedWork.car),
        selectinload(CompletedWork.service),
    ).where(CompletedWork.service_id == service_id).order_by(CompletedWork.performed_at.asc())
    works = (await db.execute(works_stmt)).scalars().all()
    user_ids = {w.client.user_id for w in works if w.client and w.client.user_id}
    vk_map = await _vk_map_for(user_ids, db)
    usernames = await _usernames_map(user_ids, db)
    tz = get_timezone(await get_schedule(db))
    work_rows = [_work_dict(w, vk_map, {}, usernames, tz) for w in works]

    price_rows_db = (await db.execute(
        select(ServicePriceHistory)
        .where(ServicePriceHistory.service_id == service_id)
        .order_by(ServicePriceHistory.changed_at.asc())
    )).scalars().all()
    price_rows = [
        {"price_from": p.price_from, "changed_at": _local_iso(p.changed_at, tz)}
        for p in price_rows_db
    ]

    service_dict = {"name": service.name, "price_from": service.price_from}
    data = build_service_export_xlsx(service_dict, work_rows, price_rows)
    safe_name = "".join(c for c in service.name if c.isalnum() or c in " -_").strip() or "услуга"
    fname = f"{safe_name}_{date.today().isoformat()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


# ─── Записи на услуги ───
@router.get("/appointments", dependencies=[Depends(require_admin)])
async def admin_appointments(db: AsyncSession = Depends(get_db)):
    stmt = select(Appointment).options(
        selectinload(Appointment.client),
        selectinload(Appointment.car),
        selectinload(Appointment.service),
    ).order_by(Appointment.start_datetime.desc())
    apps = (await db.execute(stmt)).scalars().all()
    # Фактические цены выполненных записей — для показа в карточке записи
    work_rows = (await db.execute(
        select(CompletedWork.appointment_id, CompletedWork.actual_price)
    )).all()
    price_map = {appt_id: price for appt_id, price in work_rows}
    # VK-id клиентов — основная связь с клиентом.
    user_ids = {a.client.user_id for a in apps if a.client and a.client.user_id}
    vk_map = await _vk_map_for(user_ids, db)
    tz = get_timezone(await get_schedule(db))
    return [
        {
            "id": a.id,
            "client_name": a.client.name if a.client else "—",
            "client_phone": a.client.phone if a.client else None,
            "client_vk_id": int(vk_map[a.client.user_id]) if (a.client and a.client.user_id in vk_map) else None,
            "car": f"{a.car.brand} {a.car.model}" if a.car else "—",
            "service": a.service.name if a.service else "—",
            "service_price_from": a.service.price_from if a.service else None,
            "actual_price": price_map.get(a.id),
            "start": _local_iso(a.start_datetime, tz),
            "end": _local_iso(a.end_datetime, tz),
            "status": a.status,
            "cancelled_by": a.cancelled_by,
        }
        for a in apps
    ]


@router.patch("/appointments/{appt_id}", dependencies=[Depends(require_admin)])
async def admin_update_appointment(appt_id: int, payload: AppointmentUpdate,
                                   db: AsyncSession = Depends(get_db)):
    a = await db.get(Appointment, appt_id)
    if not a:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if payload.status is not None:
        a.status = payload.status
        if a.status == "cancelled":
            a.cancelled_by = "master"

    # При завершении записи фиксируем работу в журнале (если ещё не зафиксирована)
    if a.status == "completed":
        existing = (await db.execute(
            select(CompletedWork).where(CompletedWork.appointment_id == a.id)
        )).scalar_one_or_none()
        if not existing:
            service = await db.get(Service, a.service_id)
            price = payload.actual_price if payload.actual_price is not None else (service.price_from if service else 0.0)
            db.add(CompletedWork(
                appointment_id=a.id,
                client_id=a.client_id,
                car_id=a.car_id,
                service_id=a.service_id,
                description=service.description if service else None,
                actual_price=price,
                total_amount=price,
                performed_at=a.end_datetime or func.now(),
            ))

    await db.commit()
    await db.refresh(a)
    return {"id": a.id, "status": a.status}


# ─── Журнал работ ───
def _work_dict(w, vk_map: dict = None, phones: dict = None,
               usernames: dict = None, tz=None) -> dict:
    """Словарь работы для списка и карточки (единый формат).

    `phones` — {client_id: телефон} fallback, если профиля нет.
    `usernames` — {user_id: ник VK}.
    """
    client = w.client
    phone = client.phone if client else None
    if not phone and phones and client:
        phone = phones.get(client.id)
    vk_username = (usernames or {}).get(client.user_id) if (client and client.user_id) else None
    tz = tz or ZoneInfo("UTC")
    return {
        "id": w.id,
        "appointment_id": w.appointment_id,
        "client_name": client.name if client else "—",
        "client_phone": phone,
        "client_vk_id": int(vk_map[client.user_id]) if (client and client.user_id
                         and vk_map and client.user_id in vk_map) else None,
        "client_vk_username": vk_username,
        "car": f"{w.car.brand} {w.car.model}" if w.car else "—",
        "service": w.service.name if w.service else "—",
        "description": w.description,
        "actual_price": w.actual_price,
        "total_amount": w.total_amount,
        "master_comment": w.master_comment,
        "performed_at": _local_iso(w.performed_at, tz),
        "created_at": _local_iso(w.created_at, tz),
    }


async def _vk_map_for(user_ids: set, db) -> dict:
    """VK-id клиентов по внутренним user_id — для связи с клиентом в админке."""
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(PlatformAccount.user_id, PlatformAccount.external_id)
        .where(PlatformAccount.platform == "vk", PlatformAccount.user_id.in_(user_ids))
    )).all()
    return {uid: eid for uid, eid in rows}


async def _usernames_map(user_ids: set, db) -> dict:
    """Ники VK-аккаунтов клиентов: {user_id: nickname}."""
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(PlatformAccount.user_id, PlatformAccount.username)
        .where(
            PlatformAccount.platform == "vk",
            PlatformAccount.user_id.in_(user_ids),
            PlatformAccount.username.isnot(None),
        )
    )).all()
    return {uid: username for uid, username in rows if username}


def _month_bounds(month: str | None, tz=None):
    """Границы локального месяца «YYYY-MM», переведённые в UTC для БД."""
    if not month:
        return None
    tz = tz or ZoneInfo("UTC")
    try:
        year, m = map(int, month.split("-"))
        start = datetime(year, m, 1, tzinfo=tz).astimezone(timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=tz).astimezone(timezone.utc) if m == 12 \
            else datetime(year, m + 1, 1, tzinfo=tz).astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid month")
    return start, end


@router.get("/works", dependencies=[Depends(require_admin)])
async def admin_works(month: str = None, db: AsyncSession = Depends(get_db)):
    stmt = select(CompletedWork).options(
        selectinload(CompletedWork.client),
        selectinload(CompletedWork.car),
        selectinload(CompletedWork.service),
    ).order_by(CompletedWork.performed_at.desc())
    tz = get_timezone(await get_schedule(db))
    bounds = _month_bounds(month, tz)
    if bounds:
        stmt = stmt.where(CompletedWork.performed_at >= bounds[0],
                          CompletedWork.performed_at < bounds[1])
    works = (await db.execute(stmt)).scalars().all()
    user_ids = {w.client.user_id for w in works if w.client and w.client.user_id}
    vk_map = await _vk_map_for(user_ids, db)
    phones = {}
    usernames = await _usernames_map(user_ids, db)
    return [_work_dict(w, vk_map, phones, usernames, tz) for w in works]


@router.get("/works/export", dependencies=[Depends(require_admin)])
async def admin_works_export(db: AsyncSession = Depends(get_db)):
    """Вся история оказанных услуг в одном .xlsx (журнал работ).

    Роут обязательно выше /works/{work_id}, чтобы «export» не попал в int-роут.
    """
    stmt = select(CompletedWork).options(
        selectinload(CompletedWork.client),
        selectinload(CompletedWork.car),
        selectinload(CompletedWork.service),
    ).order_by(CompletedWork.performed_at.asc())
    works = (await db.execute(stmt)).scalars().all()
    user_ids = {w.client.user_id for w in works if w.client and w.client.user_id}
    vk_map = await _vk_map_for(user_ids, db)
    phones = {}
    usernames = await _usernames_map(user_ids, db)
    tz = get_timezone(await get_schedule(db))
    rows = [_work_dict(w, vk_map, phones, usernames, tz) for w in works]
    data = build_works_xlsx(rows)
    fname = f"журнал-работ_{date.today().isoformat()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.get("/works/{work_id}", dependencies=[Depends(require_admin)])
async def admin_work(work_id: int, db: AsyncSession = Depends(get_db)):
    """Карточка одной работы (чтобы не тянуть весь журнал)."""
    stmt = select(CompletedWork).options(
        selectinload(CompletedWork.client),
        selectinload(CompletedWork.car),
        selectinload(CompletedWork.service),
    ).where(CompletedWork.id == work_id)
    w = (await db.execute(stmt)).scalars().first()
    if not w:
        raise HTTPException(status_code=404, detail="Work not found")
    user_ids = {w.client.user_id} if w.client and w.client.user_id else set()
    vk_map = await _vk_map_for(user_ids, db)
    phones = {}
    usernames = await _usernames_map(user_ids, db)
    tz = get_timezone(await get_schedule(db))
    return _work_dict(w, vk_map, phones, usernames, tz)


class WorkUpdate(BaseModel):
    actual_price: float = None
    total_amount: float = None
    master_comment: str = None


@router.patch("/works/{work_id}", dependencies=[Depends(require_admin)])
async def admin_update_work(work_id: int, payload: WorkUpdate, db: AsyncSession = Depends(get_db)):
    w = await db.get(CompletedWork, work_id)
    if not w:
        raise HTTPException(status_code=404, detail="Work not found")

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update")

    if "actual_price" in fields and "total_amount" not in fields:
        # По умолчанию сумма заказа равна фактической цене
        fields["total_amount"] = fields["actual_price"]

    for key, value in fields.items():
        setattr(w, key, value)

    await db.commit()
    await db.refresh(w)
    return {
        "id": w.id,
        "actual_price": w.actual_price,
        "total_amount": w.total_amount,
        "master_comment": w.master_comment,
    }


# ─── Статистика ───
@router.get("/stats", dependencies=[Depends(require_admin)])
async def admin_stats(days: int = None, db: AsyncSession = Depends(get_db)):
    since = None
    if days:
        since = datetime.now(timezone.utc) - timedelta(days=days)

    clients_count = (await db.execute(
        select(func.count()).select_from(Client).where(Client.is_active.is_(True))
    )).scalar()

    appt_stmt = select(Appointment.status, func.count()).group_by(Appointment.status)
    if since:
        appt_stmt = appt_stmt.where(Appointment.created_at >= since)
    appt_rows = (await db.execute(appt_stmt)).all()
    appt = {"total": 0, "booked": 0, "completed": 0, "cancelled": 0, "no_show": 0}
    for status, cnt in appt_rows:
        appt[status] = cnt
        appt["total"] += cnt

    work_stmt = select(
        func.count(),
        func.coalesce(func.sum(CompletedWork.total_amount), 0),
    )
    if since:
        work_stmt = work_stmt.where(CompletedWork.performed_at >= since)
    works_count, revenue = (await db.execute(work_stmt)).one()

    svc_stmt = (
        select(
            Service.name,
            func.count(CompletedWork.id),
            func.coalesce(func.sum(CompletedWork.total_amount), 0),
        )
        .join(CompletedWork, CompletedWork.service_id == Service.id)
        .group_by(Service.name)
        .order_by(func.sum(CompletedWork.total_amount).desc())
    )
    if since:
        svc_stmt = svc_stmt.where(CompletedWork.performed_at >= since)
    svc_rows = (await db.execute(svc_stmt)).all()

    return {
        "days": days,
        "clients_count": clients_count or 0,
        "appointments": appt,
        "works_count": works_count or 0,
        "revenue": float(revenue or 0),
        "by_service": [
            {"service": name, "count": cnt, "revenue": float(rev or 0)}
            for name, cnt, rev in svc_rows
        ],
    }


# ─── Расписание ───
@router.get("/schedule", dependencies=[Depends(require_admin)])
async def admin_schedule(db: AsyncSession = Depends(get_db)):
    return await get_schedule(db)


class ScheduleUpdate(BaseModel):
    timezone: str = None
    work_hours: str = None
    work_days: str = None
    non_working_dates: str = None
    remind_hours: str = None
    remind_hours_2: str = None


@router.patch("/schedule", dependencies=[Depends(require_admin)])
async def admin_update_schedule(payload: ScheduleUpdate, db: AsyncSession = Depends(get_db)):
    fields = payload.model_dump(exclude_unset=True)
    if "timezone" in fields:
        try:
            ZoneInfo(fields["timezone"])
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Unknown IANA timezone")
    for key, value in fields.items():
        existing = (await db.execute(
            select(Setting).where(Setting.key == key)
        )).scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
    await db.commit()
    return await get_schedule(db)


# ─── Контакты ───
@router.get("/contacts", dependencies=[Depends(require_admin)])
async def admin_contacts(db: AsyncSession = Depends(get_db)):
    return {"contacts_text": await get_contacts(db)}


class ContactsUpdate(BaseModel):
    contacts_text: str


@router.patch("/contacts", dependencies=[Depends(require_admin)])
async def admin_update_contacts(payload: ContactsUpdate, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(
        select(Setting).where(Setting.key == CONTACTS_KEY)
    )).scalar_one_or_none()
    if existing:
        existing.value = payload.contacts_text
    else:
        db.add(Setting(key=CONTACTS_KEY, value=payload.contacts_text))
    await db.commit()
    return {"contacts_text": await get_contacts(db)}
