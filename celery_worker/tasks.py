"""Периодические задачи Celery: напоминания клиентам о записях в VK.

Две стадии:
  - основное напоминание за `remind_hours` (по умолчанию 24 ч) → колонка reminded_at;
  - напоминание "скоро" за `remind_hours_2` (по умолчанию 3 ч) → колонка reminded_soon_at.

Напоминания уходят через VK API от имени сообщества.
"""
import asyncio
import json
import logging
import os
import random
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from celery import Celery

log = logging.getLogger("celery.reminders")

app = Celery(
    "tasks",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)
app.conf.timezone = "UTC"

VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN", "")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "")
VK_API_VERSION = "5.131"

DB_DSN = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

REMIND_DEFAULT_HOURS = 24  # за сколько часов напоминать (если не настроено)
REMIND_DEFAULT_HOURS_2 = 3  # за сколько часов слать напоминание "скоро" (если не настроено)
REMINDER_RETRY_BASE_MINUTES = 5  # первая повторная попытка через 5 минут
REMINDER_RETRY_MAX_MINUTES = 60  # больше 60 минут не ждём

app.conf.beat_schedule = {
    "send-appointment-reminders": {
        "task": "tasks.send_reminders",
        "schedule": 300.0,  # каждые 5 минут
    },
}


async def _get_remind_hours(conn, key: str, default: float) -> float:
    """Читает настройку из таблицы settings (иначе дефолт)."""
    row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
    if row and row["value"]:
        try:
            value = float(row["value"])
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return default


async def _get_timezone(conn):
    """Таймзона сервиса из settings — в ней показываем время в напоминании."""
    row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", "timezone")
    name = (row["value"] if row else None) or "UTC"
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, TypeError, AttributeError):
        return ZoneInfo("UTC")


def _window(remind_hours: float) -> timedelta:
    """Окно поиска: примерно 25% от интервала, но не меньше 15 и не больше 60 минут."""
    return timedelta(minutes=max(15.0, min(60.0, remind_hours * 15.0)))


def _retry_delay(failures: int) -> timedelta:
    """Задержка перед следующей попыткой: 5, 10, 20, 40, затем 60 минут."""
    minutes = REMINDER_RETRY_BASE_MINUTES * (2 ** max(0, failures - 1))
    return timedelta(minutes=min(REMINDER_RETRY_MAX_MINUTES, minutes))


async def _fetch_stage(conn, remind_hours: float, mark_col: str):
    """Записи для конкретной стадии напоминания.

    mark_col — колонка-метка: 'reminded_at' (основное) или 'reminded_soon_at' (скоро).
    Выбираются активные записи без этой метки, начало которых ~ через remind_hours.
    Напоминания шлём только клиентам с VK--аккаунтом.
    """
    now = datetime.now(timezone.utc)
    win = _window(remind_hours)
    lo = now + timedelta(hours=remind_hours) - win
    hi = now + timedelta(hours=remind_hours) + win
    return await conn.fetch(
        f"""
        SELECT a.id,
               a.start_datetime,
               s.name                                AS service_name,
               c.brand || ' ' || c.model             AS car_name,
               pa.external_id                        AS peer_id,
               a.reminder_last_error_at,
               a.reminder_failures
        FROM appointments a
        JOIN services s              ON s.id = a.service_id
        JOIN cars c                  ON c.id = a.car_id
        JOIN clients cl              ON cl.id = a.client_id
        JOIN platform_accounts pa    ON pa.user_id = cl.user_id
        WHERE a.status = 'booked'
          AND a.{mark_col} IS NULL
          AND pa.platform = 'vk'
          AND a.start_datetime >= $1
          AND a.start_datetime <= $2
        """,
        lo,
        hi,
    )


def _vk_api(method: str, **payload):
    """Прямой вызов VK API. Возвращает ``response`` или None при ошибке."""
    if not VK_GROUP_TOKEN:
        log.warning("VK API %s: VK_GROUP_TOKEN не задан, отправка пропущена", method)
        return None
    params = {
        "access_token": VK_GROUP_TOKEN,
        "v": VK_API_VERSION,
    }
    if VK_GROUP_ID and str(VK_GROUP_ID).lstrip("-").isdigit():
        params["group_id"] = abs(int(VK_GROUP_ID))
    params.update(payload)
    url = f"https://api.vk.com/method/{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.warning("VK API %s недоступен: %s: %s", method, type(exc).__name__, exc)
        return None
    if "error" in data:
        err = data["error"]
        log.error(
            "VK API %s вернул ошибку %s: %s",
            method,
            err.get("error_code"),
            err.get("error_msg"),
        )
        return None
    return data.get("response")


def _send_vk(peer_id, text: str):
    """Отправляет сообщение в VK. Возвращает message_id или None при ошибке."""
    try:
        peer = int(peer_id)
    except (TypeError, ValueError):
        log.warning("Некорректный VK peer_id для напоминания: %r", peer_id)
        return None
    result = _vk_api(
        "messages.send",
        peer_id=peer,
        message=text,
        random_id=random.randint(1, 2 ** 31 - 1),
    )
    if isinstance(result, int):
        return result
    if result is not None:
        log.warning("VK messages.send вернул неожиданный ответ: %r", result)
    return None


def _reminder_text(start: datetime, service: str, car: str, tz=None) -> str:
    when = start.astimezone(tz).strftime("%d.%m.%Y в %H:%M")
    return (
        "🚗 Напоминаем о записи!\n\n"
        f"🔧 Услуга: {service}\n"
        f"🚘 Автомобиль: {car}\n"
        f"📅 {when}\n\n"
        "Ждём вас в «Service Company»! 😊"
    )


def _reminder_soon_text(start: datetime, service: str, car: str, tz=None) -> str:
    when = start.astimezone(tz).strftime("%d.%m в %H:%M")
    return (
        "⏰ Запись уже скоро!\n\n"
        f"🔧 Услуга: {service}\n"
        f"🚘 Автомобиль: {car}\n"
        f"📅 {when}\n\n"
        "Ждём вас в «Service Company»! 😊"
    )


async def _run_stage(conn, remind_hours: float, mark_col: str, text_fn, tz=None) -> int:
    """Одна стадия: выборка → отправка → метка или отложенная повторная попытка."""
    rows = await _fetch_stage(conn, remind_hours, mark_col)
    sent = 0
    for r in rows:
        now = datetime.now(timezone.utc)
        failures = int(r["reminder_failures"] or 0)
        last_error = r["reminder_last_error_at"]
        if last_error is not None and last_error.tzinfo is None:
            last_error = last_error.replace(tzinfo=timezone.utc)
        if last_error is not None and now - last_error < _retry_delay(failures):
            continue

        text = text_fn(r["start_datetime"], r["service_name"], r["car_name"], tz)
        if _send_vk(r["peer_id"], text):
            await conn.execute(
                f"""
                UPDATE appointments
                SET {mark_col} = $1,
                    reminder_last_error_at = NULL,
                    reminder_failures = 0
                WHERE id = $2
                """,
                now,
                r["id"],
            )
            sent += 1
            log.info("Напоминание отправлено: запись #%s (%s)", r["id"], mark_col)
        else:
            await conn.execute(
                """
                UPDATE appointments
                SET reminder_last_error_at = $1,
                    reminder_failures = COALESCE(reminder_failures, 0) + 1
                WHERE id = $2
                """,
                now,
                r["id"],
            )
            log.warning(
                "Напоминание не отправлено: запись #%s (%s), неудач подряд %s, "
                "следующая попытка не раньше чем через %s",
                r["id"],
                mark_col,
                failures + 1,
                _retry_delay(failures + 1),
            )
    return sent


@app.task
def send_reminders():
    """Отправляет напоминания в VK: основное и «скоро»."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DB_DSN)
        try:
            remind_hours = await _get_remind_hours(conn, "remind_hours", REMIND_DEFAULT_HOURS)
            remind_hours_2 = await _get_remind_hours(conn, "remind_hours_2", REMIND_DEFAULT_HOURS_2)
            tz = await _get_timezone(conn)
            checked_main = await _run_stage(conn, remind_hours, "reminded_at", _reminder_text, tz)
            checked_soon = await _run_stage(conn, remind_hours_2, "reminded_soon_at", _reminder_soon_text, tz)
            result = {
                "checked": checked_main + checked_soon,
                "sent": checked_main + checked_soon,
                "main": {"checked": checked_main, "sent": checked_main},
                "soon": {"checked": checked_soon, "sent": checked_soon},
            }
            log.info(
                "Напоминания: отправлено %s из %s (основные %s, скоро %s)",
                result["sent"],
                result["checked"],
                checked_main,
                checked_soon,
            )
            return result
        finally:
            await conn.close()

    return asyncio.run(run())
