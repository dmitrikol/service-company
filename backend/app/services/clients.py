"""Склейка клиентов по номеру телефона.

Клиент регистрируется в backend по заголовкам platform/user-id. Если номер
телефона совпадает с уже существующим клиентом, новая регистрация не создаёт
дубликат: аккаунт привязывается к найденной карточке.
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.user import User, PlatformAccount
from app.models.car import Car
from app.models.appointment import Appointment
from app.models.completed_work import CompletedWork


def normalize_phone(p: str | None) -> str | None:
    """Телефон для сравнения: только цифры, без ведущей 7/8.

    «+7 (900) 000-00-00» и «89000000000» дают один ключ «9000000000».
    """
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = digits[1:]
    return digits or None


async def find_client_by_phone(db: AsyncSession, phone: str) -> Client | None:
    """Активный клиент с таким номером (свежий по id), иначе None."""
    norm = normalize_phone(phone)
    if not norm:
        return None
    clients = (await db.execute(
        select(Client)
        .where(Client.is_active.is_(True), Client.phone.isnot(None))
        .order_by(Client.id.desc())
    )).scalars().all()
    for c in clients:
        if normalize_phone(c.phone) == norm:
            return c
    return None


async def attach_account_to_client(
    db: AsyncSession, client: Client, *,
    platform: str, external_id: str,
    first_name: str | None = None, last_name: str | None = None,
    username: str | None = None, phone: str | None = None,
) -> int:
    """Привязывает новый аккаунт платформы к клиенту (и создаёт User при нужде).

    Вызывается, когда у платформы ещё нет аккаунта, но номер телефона уже
    принадлежит существующему клиенту. Возвращает id user клиента.
    """
    if client.user_id is None:
        user = User()
        db.add(user)
        await db.flush()
        client.user_id = user.id
    db.add(PlatformAccount(
        user_id=client.user_id,
        platform=platform,
        external_id=external_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        phone=phone,
    ))
    if phone and phone.strip():
        client.phone = phone.strip()
    if first_name and (not client.name or client.name == "Клиент"):
        client.name = first_name
    await db.commit()
    return client.user_id


async def merge_client_into(db: AsyncSession, from_client: Client, to_client: Client) -> None:
    """Переносит всё с from_client на to_client и удаляет дубликат.

    Используется, когда телефон ввёл клиент платформы, у которого ещё нет
    номера: аккаунты, машины, записи и работы переносятся на найденного по
    телефону клиента, чтобы карточка осталась одна.

    Сессию не коммитит: вызывающий код решает, когда зафиксировать изменения,
    чтобы ошибка позже в запросе не оставила частично слитую карточку.
    """
    if from_client.id == to_client.id:
        return
    # У целевого клиента (например, добавленного вручную) может не быть user —
    # создаём, чтобы было куда перенести аккаунты платформ
    if to_client.user_id is None:
        user = User()
        db.add(user)
        await db.flush()
        to_client.user_id = user.id
    # Аккаунты платформ переносим на user целевого клиента
    if from_client.user_id and from_client.user_id != to_client.user_id:
        accounts = (await db.execute(
            select(PlatformAccount).where(PlatformAccount.user_id == from_client.user_id)
        )).scalars().all()
        for acc in accounts:
            acc.user_id = to_client.user_id
    # Машины, записи и выполненные работы
    await db.execute(update(Car).where(Car.client_id == from_client.id)
                     .values(client_id=to_client.id))
    await db.execute(update(Appointment).where(Appointment.client_id == from_client.id)
                     .values(client_id=to_client.id))
    await db.execute(update(CompletedWork).where(CompletedWork.client_id == from_client.id)
                     .values(client_id=to_client.id))
    if not to_client.name or to_client.name == "Клиент":
        to_client.name = from_client.name or to_client.name
    await db.delete(from_client)
