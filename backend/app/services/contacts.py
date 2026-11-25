"""Контакты сервиса для экрана «Контакты» у клиента.

Хранятся в таблице settings (key-value) под ключом `contacts_text` — тело
текста без заголовка (заголовок добавляет бот). Пустое значение = дефолт.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.setting import Setting

CONTACTS_KEY = "contacts_text"

CONTACTS_DEFAULT = (
    "📍 <b>Адрес:</b> г. Москва, ул. Примерная, д. 1\n"
    "📞 <b>Телефон:</b> +7 (900) 000-00-00\n"
    "🕐 <b>Часы работы:</b> 09:00 – 20:00, без выходных\n\n"
    "Ответим на вопросы и подберём удобное время. 😊"
)


async def get_contacts(db: AsyncSession) -> str:
    """Текущий текст контактов (с дефолтом, если ещё не задан)."""
    row = (await db.execute(
        select(Setting).where(Setting.key == CONTACTS_KEY)
    )).scalar_one_or_none()
    return row.value if row and row.value else CONTACTS_DEFAULT
