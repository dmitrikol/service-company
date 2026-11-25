"""Расчёт доступных дат/времени по расписанию сервиса.

Логика повторяет правила backend/app/services/schedule.py, но без завязки на
конкретный тип клавиатуры: здесь только даты/строки, а рисует их keyboards.py.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SLOT_STEP_MINUTES = 30
WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_SHORT = ("янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек")


def service_timezone(schedule: dict) -> ZoneInfo:
    """Таймзона сервиса из настроек; битое значение → UTC."""
    try:
        return ZoneInfo((schedule.get("timezone") or "UTC").strip())
    except (ZoneInfoNotFoundError, ValueError, TypeError, AttributeError):
        return ZoneInfo("UTC")


def date_label(d: date) -> str:
    """«16 авг (Сб)»."""
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} ({WEEKDAYS_SHORT[d.weekday()]})"


def parse_work_hours(hours_str: str):
    """'09:00-20:00' -> (time(9,0), time(20,0)) или None при неверном формате."""
    try:
        parts = (hours_str or "").replace(" ", "").split("-")
        return time.fromisoformat(parts[0]), time.fromisoformat(parts[1])
    except (ValueError, IndexError):
        return None


def day_available(d: date, schedule: dict) -> bool:
    """Доступен ли день для записи: не в прошлом, не выходной, не нерабочая дата."""
    if d < datetime.now(service_timezone(schedule)).date():
        return False
    dates = {x.strip() for x in (schedule.get("non_working_dates") or "").split(",") if x.strip()}
    if d.strftime("%d.%m.%Y") in dates:
        return False
    work_days = {int(x) for x in (schedule.get("work_days") or "").split(",") if x.strip().isdigit()}
    if work_days and d.isoweekday() not in work_days:
        return False
    return True


def next_available_days(schedule: dict, count: int = 9, skip: int = 0,
                        horizon_days: int = 90) -> list[date]:
    """Следующие `count` доступных дней, пропустив первые `skip` (для «Ещё даты»)."""
    found: list[date] = []
    skipped = 0
    for offset in range(horizon_days):
        d = datetime.now(service_timezone(schedule)).date() + timedelta(days=offset)
        if not day_available(d, schedule):
            continue
        if skipped < skip:
            skipped += 1
            continue
        found.append(d)
        if len(found) >= count:
            break
    return found


def _parse_busy_slot(raw: dict):
    try:
        start = datetime.fromisoformat(raw["start"]).replace(tzinfo=None)
        end = datetime.fromisoformat(raw["end"]).replace(tzinfo=None)
        return start, end
    except (KeyError, TypeError, ValueError):
        return None


def _is_busy(slot_start: datetime, slot_end: datetime, busy: list | None) -> bool:
    if not busy:
        return False
    for raw in busy:
        interval = _parse_busy_slot(raw)
        if interval and slot_start < interval[1] and interval[0] < slot_end:
            return True
    return False


def available_times(day: date, duration_minutes: int, schedule: dict,
                    busy: list | None = None) -> list[str]:
    """Свободные HH:MM на день с учётом длительности услуги и занятости."""
    hours = parse_work_hours(schedule.get("work_hours") or "")
    if not hours:
        return []
    open_t, close_t = hours
    now = datetime.now(service_timezone(schedule)).replace(tzinfo=None)
    slot = timedelta(minutes=SLOT_STEP_MINUTES)
    start = datetime.combine(day, open_t)
    end_of_day = datetime.combine(day, close_t)
    out: list[str] = []
    while start + timedelta(minutes=duration_minutes or 0) <= end_of_day:
        if start > now:
            slot_end = start + timedelta(minutes=duration_minutes or 0)
            if not _is_busy(start, slot_end, busy):
                out.append(start.strftime("%H:%M"))
        start += slot
    return out
