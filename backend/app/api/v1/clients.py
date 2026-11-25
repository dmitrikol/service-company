from fastapi import APIRouter, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.user import User, PlatformAccount
from app.models.client import Client
from app.services.clients import find_client_by_phone, attach_account_to_client, merge_client_into
from sqlalchemy import select

router = APIRouter(tags=["clients"])

@router.get("/clients/me")
async def get_me(
    platform: str = Header(...),   # "vk"
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Профиль клиента: имя + телефон — чтобы бот знал, спрашивать ли телефон при записи."""
    user = await _get_user(db, platform, user_id)
    client = (await db.execute(
        select(Client).where(Client.user_id == user.id)
    )).scalars().first()
    return {
        "name": client.name if client else None,
        "phone": client.phone if client else None,
    }


@router.patch("/clients/me")
async def update_me(
    name: str = None,
    phone: str = None,
    platform: str = Header(...),
    user_id: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Клиент правит своё имя/телефон (например, сменил номер).

    Если новый телефон уже принадлежит другому активному клиенту (тот же
    человек когда-то писал с другой платформы) — карточки склеиваются, как и
    при вводе телефона во время записи.
    """
    user = await _get_user(db, platform, user_id)
    client = (await db.execute(
        select(Client).where(Client.user_id == user.id)
    )).scalars().first()
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found")

    if name is not None and name.strip():
        client.name = name.strip()

    if phone is not None:
        phone = phone.strip()
        if phone:
            matched = await find_client_by_phone(db, phone)
            if matched and matched.id != client.id:
                await merge_client_into(db, from_client=client, to_client=matched)
                client = matched
            client.phone = phone
        else:
            client.phone = None

    await db.commit()
    await db.refresh(client)
    return {"id": client.id, "name": client.name, "phone": client.phone}


@router.post("/users/register")
async def register_user(
    platform: str = Header(...),   # "vk"
    user_id: str = Header(...),    # ID пользователя в платформе
    first_name: str = None,
    last_name: str = None,
    username: str = None,
    phone: str = None,
    db: AsyncSession = Depends(get_db)
):
    # Проверяем, нет ли уже такого аккаунта
    stmt = select(PlatformAccount).where(
        PlatformAccount.platform == platform,
        PlatformAccount.external_id == user_id
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing:
        # Гарантируем наличие клиентского профиля (если был создан до этого фикса)
        client = (await db.execute(
            select(Client).where(Client.user_id == existing.user_id)
        )).scalars().first()
        if not client:
            db.add(Client(
                user_id=existing.user_id,
                name=existing.first_name or existing.username or "Клиент",
                phone=existing.phone
            ))
            await db.commit()
        else:
            # Подтягиваем телефон, если он появился только сейчас
            if phone and phone.strip() and not client.phone:
                client.phone = phone.strip()
                existing.phone = phone.strip()
                await db.commit()
        return {"user_id": existing.user_id, "message": "Already registered"}

    # Если передали телефон и он уже есть у активного клиента — это тот же
    # человек на другой платформе: привязываем аккаунт к его карточке
    if phone and phone.strip():
        matched = await find_client_by_phone(db, phone)
        if matched:
            uid = await attach_account_to_client(
                db, matched,
                platform=platform, external_id=user_id,
                first_name=first_name, last_name=last_name,
                username=username, phone=phone,
            )
            return {"user_id": uid, "message": "Linked by phone"}

    # Создаём User и Client (если переданы имя/телефон)
    new_user = User()
    db.add(new_user)
    await db.flush()

    pa = PlatformAccount(
        user_id=new_user.id,
        platform=platform,
        external_id=user_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        phone=phone
    )
    db.add(pa)

    # Клиентский профиль создаётся всегда (телефон может заполнить позже)
    db.add(Client(
        user_id=new_user.id,
        name=first_name or username or "Клиент",
        phone=phone
    ))

    await db.commit()
    return {"user_id": new_user.id, "message": "Registered successfully"}


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