"""Логика рабочего расписания сервиса.

Расписание хранится в таблице settings (key-value):
    timezone            — IANA-имя, например "Europe/Moscow" (по умолчанию UTC)
    work_hours          — "09:00-20:00" (в этой таймзоне)
    work_days           — "1,2,3,4,5,6,7" (1 — Пн, 7 — Вс)
    non_working_dates   — "01.05.2026, 09.05.2026" (пусто = нет)

Все времена в БД хранятся в UTC; часы/даты расписания задаются в `timezone`.
"""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.setting import Setting

SCHEDULE_DEFAULTS = {
    "timezone": "UTC",  # IANA-имя: Europe/Moscow, Asia/Yekaterinburg и т.д.
    "work_hours": "09:00-20:00",
    "work_days": "1,2,3,4,5,6,7",
    "non_working_dates": "",
    "remind_hours": "24",  # за сколько часов напоминать клиенту о записи
    "remind_hours_2": "3",  # за сколько часов слать второе напоминание "скоро"
}
SCHEDULE_KEYS = tuple(SCHEDULE_DEFAULTS.keys())


def get_timezone(schedule: dict) -> ZoneInfo:
    """Таймзона сервиса из настроек; неизвестное/битое значение → UTC."""
    name = (schedule.get("timezone") or "UTC").strip()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("UTC")


async def get_schedule(db: AsyncSession) -> dict:
    """Читает настройки расписания из таблицы settings (с дефолтами)."""
    rows = (await db.execute(
        select(Setting).where(Setting.key.in_(SCHEDULE_KEYS))
    )).scalars().all()
    data = {r.key: r.value for r in rows}
    return {
        key: data.get(key) if data.get(key) else SCHEDULE_DEFAULTS[key]
        for key in SCHEDULE_KEYS
    }


def parse_work_hours(hours_str: str):
    """'09:00-20:00' -> (time(9, 0), time(20, 0)) или None при неверном формате."""
    try:
        parts = hours_str.replace(" ", "").split("-")
        return time.fromisoformat(parts[0]), time.fromisoformat(parts[1])
    except (ValueError, IndexError):
        return None


def _parse_dates(dates_str: str) -> set:
    return {d.strip() for d in (dates_str or "").split(",") if d.strip()}


def _parse_days(days_str: str) -> set:
    days = set()
    for part in (days_str or "").split(","):
        part = part.strip()
        if part.isdigit():
            days.add(int(part))
    return days


def validate_schedule(start: datetime, end: datetime, schedule: dict) -> str | None:
    """Проверяет интервал [start, end] по рабочему расписанию.

    Возвращает текст ошибки (уже на русском) или None, если время подходит.
    """
    tz = get_timezone(schedule)

    # Боты присылают время без таймзоны — это локальное время сервиса.
    # Aware-значения (например, из БД) просто переводим в эту же таймзону.
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    else:
        start = start.astimezone(tz)
    if end.tzinfo is None:
        end = end.replace(tzinfo=tz)
    else:
        end = end.astimezone(tz)

    now = datetime.now(tz)
    if start < now:
        return "Это время уже прошло. Выберите будущее время. ⏰"

    if start.strftime("%d.%m.%Y") in _parse_dates(schedule.get("non_working_dates")):
        return "В эту дату у нас выходной день. 🙁 Выберите другую дату."

    work_days = _parse_days(schedule.get("work_days"))
    if work_days and start.isoweekday() not in work_days:
        return "В выбранный день мы не работаем. 🙁 Выберите другой день."

    hours = parse_work_hours(schedule.get("work_hours"))
    if hours:
        open_t, close_t = hours
        if start.time() < open_t or end.time() > close_t:
            return (
                f"Мы работаем с {open_t.strftime('%H:%M')} до "
                f"{close_t.strftime('%H:%M')}. Выберите время в этом интервале. ⏰"
            )
    return None
