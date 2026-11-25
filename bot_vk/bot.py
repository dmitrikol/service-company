"""VK-бот «Вмятый Элемент» — клиентский сценарий: запись на услуги.

Работает с тем же клиентским REST API backend'а (platform="vk"), но с
VK-специфичным UI: обычные (не inline) клавиатуры максимум по 4 кнопки в ряд —
поэтому даты показываются списком ближайших доступных дней вместо календаря.

Состояние диалога — простое хранилище в памяти (state.py), без vkbottle FSM:
это осознанный выбор ради предсказуемости и меньшей зависимости от деталей
конкретной версии vkbottle (см. PROJECT_MEMORY/changes.md).
"""
import logging
import re
import time as _time
from datetime import date, datetime

from vkbottle.api import API
from vkbottle.bot import Bot, Message
from vkbottle.http import AiohttpClient

# VK не рендерит HTML-теги в сообщениях — contacts_text приходит с backend'а
# с разметкой, поэтому срезаем теги перед отправкой.
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_RU_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def _ru_when(dt: datetime) -> str:
    return f"{dt.day} {_RU_MONTHS[dt.month]} {dt.strftime('%H:%M')}"


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text or "")

from config import VK_GROUP_TOKEN
from api_client import ApiClient
from state import get_session, reset_session
from schedule_utils import next_available_days, available_times, date_label
from vk_notify import notify_new_appointment, notify_cancelled
import keyboards as kb
import texts as t

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("vk_bot")

DATES_PAGE_SIZE = 9


def _num(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(v)) if v == int(v) else f"{v:.2f}"


VK_BUTTON_LABEL_LIMIT = 40


def _vk_button_label(label: str) -> str:
    """VK API отклоняет ВСЮ клавиатуру, если хоть одна подпись кнопки длиннее
    40 символов (ошибка 911) — обрезаем с многоточием, чтобы не терять всё
    сообщение целиком из-за одного длинного названия услуги/авто."""
    if len(label) <= VK_BUTTON_LABEL_LIMIT:
        return label
    return label[:VK_BUTTON_LABEL_LIMIT - 1].rstrip() + "…"


async def _ensure_registered(bot: Bot, message: Message, session: dict) -> None:
    """Регистрирует VK-аккаунт в backend (идемпотентно)."""
    if session.get("registered"):
        return
    first_name = last_name = None
    try:
        users = await bot.api.users.get(user_ids=[message.from_id])
        if users:
            first_name = users[0].first_name
            last_name = users[0].last_name
    except Exception:
        pass  # не критично — зарегистрируем без имени, его можно будет узнать позже
    api = ApiClient(user_id=str(message.from_id))
    try:
        resp = await api.register(first_name=first_name, last_name=last_name)
    except Exception:
        log.exception("registration request failed for vk user %s", message.from_id)
        resp = None
    # Помечаем зарегистрированным, только если backend реально ответил (запись
    # уже существует либо создана только что) — иначе при следующем сообщении
    # повторим попытку, а не будем молча считать пользователя зарегистрированным.
    if isinstance(resp, dict) and "user_id" in resp:
        session["registered"] = True
    session["display_name"] = first_name or "Клиент"


async def show_main_menu(message: Message, extra: str = "") -> None:
    text = (extra + "\n\n" + t.MAIN_MENU_HINT) if extra else t.WELCOME
    await message.answer(text, keyboard=kb.main_menu_kb())


def _restart_flow(message: Message, session: dict) -> None:
    """Начинает новый сценарий (запись/мои записи), но не забывает регистрацию/имя."""
    registered = session.get("registered")
    display_name = session.get("display_name")
    reset_session(message.from_id)
    fresh = get_session(message.from_id)
    fresh["registered"] = registered
    fresh["display_name"] = display_name


# ─── Запись на услугу ───

async def start_booking(message: Message, session: dict) -> None:
    api = ApiClient(user_id=str(message.from_id))
    services = await api.get_services()
    if not isinstance(services, list) or not services:
        await show_main_menu(message, t.NO_SERVICES)
        return
    labels = [_vk_button_label(f"{s['name']} — {_num(s['price_from'])}₽") for s in services]
    session["step"] = "choosing_service"
    session["choices"] = {label: s for label, s in zip(labels, services)}
    await message.answer(t.CHOOSE_SERVICE, keyboard=kb.choices_kb(labels, per_row=1, extra_rows=[[t.CMD_CANCEL]]))


async def on_service_chosen(message: Message, session: dict, text: str) -> None:
    service = session.get("choices", {}).get(text)
    if not service:
        await message.answer(t.UNKNOWN_CHOICE)
        return
    session["service_id"] = service["id"]
    session["service_name"] = service["name"]
    session["duration"] = service["duration_minutes"]
    await _after_service_chosen(message, session)


async def _after_service_chosen(message: Message, session: dict) -> None:
    api = ApiClient(user_id=str(message.from_id))
    cars = await api.get_my_cars()
    if not isinstance(cars, list):
        cars = []
    if not cars:
        session["step"] = "adding_car"
        await message.answer(t.ENTER_CAR_FIRST, keyboard=kb.add_car_kb())
        return
    session["cars"] = cars
    if len(cars) == 1:
        session["car_id"] = cars[0]["id"]
        session["car_label"] = f"{cars[0]['brand']} {cars[0]['model']}"
        await _go_to_date_step(message, session)
        return
    labels = [_vk_button_label(f"{c['brand']} {c['model']}") for c in cars]
    session["step"] = "choosing_car"
    session["choices"] = {label: c for label, c in zip(labels, cars)}
    await message.answer(t.CHOOSE_CAR, keyboard=kb.cars_kb(labels))


async def on_car_chosen(message: Message, session: dict, text: str) -> None:
    if text == t.CMD_ADD_CAR:
        session["step"] = "adding_car"
        await message.answer(t.ENTER_CAR_FIRST, keyboard=kb.add_car_kb())
        return
    car = session.get("choices", {}).get(text)
    if not car:
        await message.answer(t.UNKNOWN_CHOICE)
        return
    session["car_id"] = car["id"]
    session["car_label"] = f"{car['brand']} {car['model']}"
    await _go_to_date_step(message, session)


async def on_adding_car(message: Message, session: dict, text: str) -> None:
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(t.WRONG_CAR_FORMAT, keyboard=kb.add_car_kb())
        return
    brand, model = parts
    api = ApiClient(user_id=str(message.from_id))
    resp = await api.add_car(brand, model)
    if not isinstance(resp, dict) or "id" not in resp:
        await message.answer(t.CAR_ADD_FAILED, keyboard=kb.add_car_kb())
        return
    session["car_id"] = resp["id"]
    session["car_label"] = f"{brand} {model}"
    await _go_to_date_step(message, session)


# ─── Выбор даты/времени ───

async def _go_to_date_step(message: Message, session: dict, skip: int = 0) -> None:
    api = ApiClient(user_id=str(message.from_id))
    schedule = await api.get_schedule()
    if not isinstance(schedule, dict):
        schedule = {}
    session["schedule"] = schedule
    days = next_available_days(schedule, count=DATES_PAGE_SIZE, skip=skip)
    if not days and skip == 0:
        await show_main_menu(message, t.NO_DATES_AVAILABLE)
        session.clear()
        return
    if not days:
        # «Ещё даты» упёрлось в горизонт поиска — молча остаёмся на прежнем экране
        await message.answer(t.NO_DATES_AVAILABLE)
        return
    more = next_available_days(schedule, count=1, skip=skip + len(days))
    labels = [date_label(d) for d in days]
    session["date_choices"] = {date_label(d): d for d in days}
    session["dates_skip"] = skip
    session["dates_has_more"] = bool(more)
    session["step"] = "choosing_date"
    await message.answer(t.CHOOSE_DATE, keyboard=kb.dates_kb(labels, has_more=bool(more)))


async def on_date_chosen(message: Message, session: dict, text: str) -> None:
    if text == t.CMD_MORE_DATES:
        await _go_to_date_step(message, session, skip=session.get("dates_skip", 0) + DATES_PAGE_SIZE)
        return
    d = session.get("date_choices", {}).get(text)
    if not d:
        await message.answer(t.UNKNOWN_CHOICE)
        return
    session["chosen_date"] = d
    api = ApiClient(user_id=str(message.from_id))
    busy = await api.get_busy_slots(d.isoformat(), service_id=session.get("service_id"))
    if not isinstance(busy, list):
        busy = []
    times = available_times(d, session.get("duration") or 0, session.get("schedule") or {}, busy)
    if not times:
        await message.answer(t.NO_TIMES_AVAILABLE, keyboard=kb.dates_kb(
            list(session.get("date_choices", {}).keys()), has_more=session.get("dates_has_more", False)))
        return
    session["time_choices"] = set(times)
    session["step"] = "choosing_time"
    await message.answer(t.CHOOSE_TIME.format(date=date_label(d)), keyboard=kb.times_kb(times))


async def on_time_chosen(message: Message, session: dict, text: str) -> None:
    if text == t.CMD_BACK:
        await _go_to_date_step(message, session, skip=session.get("dates_skip", 0))
        return
    if text not in session.get("time_choices", set()):
        await message.answer(t.UNKNOWN_CHOICE)
        return
    d: date = session["chosen_date"]
    hh, mm = text.split(":")
    session["start_datetime"] = datetime(d.year, d.month, d.day, int(hh), int(mm))
    await _after_time_chosen(message, session)


async def _after_time_chosen(message: Message, session: dict) -> None:
    api = ApiClient(user_id=str(message.from_id))
    me = await api.get_me()
    phone = (me or {}).get("phone") if isinstance(me, dict) else None
    if phone:
        session["phone"] = phone
        await _show_confirm(message, session)
        return
    session["step"] = "entering_phone"
    await message.answer(t.ASK_PHONE, keyboard=kb.phone_kb())


async def on_entering_phone(message: Message, session: dict, text: str) -> None:
    session["phone"] = "" if text == t.CMD_SKIP_PHONE else text.strip()
    await _show_confirm(message, session)


async def _show_confirm(message: Message, session: dict) -> None:
    session["step"] = "confirming"
    when = _ru_when(session["start_datetime"])
    text = t.CONFIRM_APPOINTMENT.format(
        service=session.get("service_name", "—"),
        car=session.get("car_label", "—"),
        when=when,
        phone=session.get("phone") or "не указан",
    )
    await message.answer(text, keyboard=kb.confirm_kb())


async def on_confirming(message: Message, session: dict, text: str) -> None:
    if text != t.CMD_CONFIRM:
        await message.answer(t.UNKNOWN_CHOICE)
        return
    api = ApiClient(user_id=str(message.from_id))
    status, resp = await api.create_appointment(
        car_id=session["car_id"],
        service_id=session["service_id"],
        start_datetime=session["start_datetime"].isoformat(),
        phone=session.get("phone") or None,
    )
    when = _ru_when(session["start_datetime"])
    if status == 200 and isinstance(resp, dict) and "id" in resp:
        await message.answer(t.APPOINTMENT_CREATED.format(when=when), keyboard=kb.main_menu_kb())
        await notify_new_appointment(
            client_name=session.get("display_name") or "Клиент",
            service=session.get("service_name", "—"),
            car=session.get("car_label", "—"),
            when=when,
            phone=session.get("phone") or "",
            vk_user_id=message.from_id,
        )
    else:
        detail = resp.get("detail", "неизвестная ошибка") if isinstance(resp, dict) else "неизвестная ошибка"
        await message.answer(t.APPOINTMENT_FAILED.format(detail=detail), keyboard=kb.main_menu_kb())
    reset_session(message.from_id)


# ─── Мои записи / отмена ───

async def show_my_appointments(message: Message, session: dict) -> None:
    api = ApiClient(user_id=str(message.from_id))
    apps = await api.get_my_appointments()
    if not isinstance(apps, list):
        apps = []
    booked = [a for a in apps if a.get("status") == "booked"]
    if not booked:
        await show_main_menu(message, t.MY_APPOINTMENTS_EMPTY)
        return
    labels = []
    choices = {}
    for a in booked:
        when = _ru_when(datetime.fromisoformat(a["start"]))
        label = _vk_button_label(f"❌ {a['service']} · {when}")
        labels.append(label)
        choices[label] = {**a, "when": when}
    session["step"] = "my_appointments"
    session["appt_choices"] = choices
    lines = [t.appointment_line({**a, "when": _ru_when(datetime.fromisoformat(a['start']))})
            for a in booked]
    await message.answer(
        t.MY_APPOINTMENTS_TITLE + "\n\n" + "\n".join(lines),
        keyboard=kb.my_appointments_kb(labels))


async def on_my_appointments_choice(message: Message, session: dict, text: str) -> None:
    if text == t.CMD_BACK:
        reset_session(message.from_id)
        await show_main_menu(message)
        return
    a = session.get("appt_choices", {}).get(text)
    if not a:
        await message.answer(t.UNKNOWN_CHOICE)
        return
    session["cancel_target"] = a
    session["step"] = "cancel_confirm"
    await message.answer(
        t.CANCEL_CONFIRM.format(service=a["service"], when=a["when"]),
        keyboard=kb.cancel_confirm_kb())


async def on_cancel_confirm(message: Message, session: dict, text: str) -> None:
    a = session.get("cancel_target")
    if text != t.CMD_YES_CANCEL or not a:
        await show_main_menu(message)
        reset_session(message.from_id)
        return
    api = ApiClient(user_id=str(message.from_id))
    status, resp = await api.cancel_appointment(a["id"])
    if status == 200:
        await message.answer(t.APPOINTMENT_CANCELLED, keyboard=kb.main_menu_kb())
        await notify_cancelled(
            client_name=session.get("display_name") or "Клиент",
            service=a["service"], car=a["car"], when=a["when"])
    else:
        detail = resp.get("detail", "неизвестная ошибка") if isinstance(resp, dict) else "неизвестная ошибка"
        await message.answer(t.APPOINTMENT_CANCEL_FAILED.format(detail=detail), keyboard=kb.main_menu_kb())
    reset_session(message.from_id)


# ─── Мои авто ───

async def show_my_cars(message: Message, session: dict) -> None:
    api = ApiClient(user_id=str(message.from_id))
    cars = await api.get_my_cars()
    if not isinstance(cars, list):
        cars = []
    session["step"] = "my_cars"
    if not cars:
        await message.answer(t.MY_CARS_EMPTY, keyboard=kb.my_cars_kb())
        return
    lines = [t.car_line(c) for c in cars]
    await message.answer(t.MY_CARS_TITLE + "\n\n" + "\n".join(lines), keyboard=kb.my_cars_kb())


async def on_my_cars_step(message: Message, session: dict, text: str) -> None:
    if text == t.CMD_ADD_CAR:
        session["step"] = "adding_car_standalone"
        await message.answer(t.ENTER_CAR_FIRST, keyboard=kb.back_only_kb())
        return
    await message.answer(t.UNKNOWN_CHOICE)


async def on_adding_car_standalone(message: Message, session: dict, text: str) -> None:
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(t.WRONG_CAR_FORMAT, keyboard=kb.back_only_kb())
        return
    brand, model = parts
    api = ApiClient(user_id=str(message.from_id))
    resp = await api.add_car(brand, model)
    if not isinstance(resp, dict) or "id" not in resp:
        await message.answer(t.CAR_ADD_FAILED, keyboard=kb.back_only_kb())
        return
    await show_main_menu(message, "✅ Автомобиль добавлен.")
    reset_session(message.from_id)


# ─── История работ ───

async def show_work_history(message: Message) -> None:
    api = ApiClient(user_id=str(message.from_id))
    works = await api.get_my_works()
    if not isinstance(works, list):
        works = []
    if not works:
        await show_main_menu(message, t.WORK_HISTORY_EMPTY)
        return
    lines = [t.work_line(w) for w in works]
    await message.answer(t.WORK_HISTORY_TITLE + "\n\n" + "\n".join(lines), keyboard=kb.main_menu_kb())


# ─── Профиль ───

async def show_profile(message: Message, session: dict) -> None:
    api = ApiClient(user_id=str(message.from_id))
    me = await api.get_me()
    if not isinstance(me, dict):
        me = {}
    session["step"] = "profile"
    await message.answer(t.profile_text(me), keyboard=kb.profile_kb())


async def on_profile_step(message: Message, session: dict, text: str) -> None:
    if text == t.CMD_EDIT_NAME:
        session["step"] = "editing_name"
        await message.answer(t.ASK_NEW_NAME, keyboard=kb.back_only_kb())
        return
    if text == t.CMD_EDIT_PHONE:
        session["step"] = "editing_phone"
        await message.answer(t.ASK_NEW_PHONE, keyboard=kb.back_only_kb())
        return
    await message.answer(t.UNKNOWN_CHOICE)


async def on_editing_name(message: Message, session: dict, text: str) -> None:
    api = ApiClient(user_id=str(message.from_id))
    resp = await api.update_profile(name=text.strip())
    await _after_profile_edit(message, resp)


async def on_editing_phone(message: Message, session: dict, text: str) -> None:
    api = ApiClient(user_id=str(message.from_id))
    resp = await api.update_profile(phone=text.strip())
    await _after_profile_edit(message, resp)


async def _after_profile_edit(message: Message, resp) -> None:
    if isinstance(resp, dict) and "id" in resp:
        await show_main_menu(message, t.PROFILE_UPDATED)
    else:
        detail = resp.get("detail", "неизвестная ошибка") if isinstance(resp, dict) else "неизвестная ошибка"
        await show_main_menu(message, t.PROFILE_UPDATE_FAILED.format(detail=detail))
    reset_session(message.from_id)


# ─── Контакты ───

async def show_contacts(message: Message) -> None:
    api = ApiClient(user_id=str(message.from_id))
    resp = await api.get_contacts()
    text = (resp or {}).get("contacts_text") if isinstance(resp, dict) else None
    await message.answer(_strip_html(text or t.CONTACTS_FAILED), keyboard=kb.main_menu_kb())


# ─── Диспетчер ───

_STEP_HANDLERS = {
    "choosing_service": on_service_chosen,
    "choosing_car": on_car_chosen,
    "adding_car": on_adding_car,
    "choosing_date": on_date_chosen,
    "choosing_time": on_time_chosen,
    "entering_phone": on_entering_phone,
    "confirming": on_confirming,
    "my_appointments": on_my_appointments_choice,
    "cancel_confirm": on_cancel_confirm,
    "my_cars": on_my_cars_step,
    "adding_car_standalone": on_adding_car_standalone,
    "profile": on_profile_step,
    "editing_name": on_editing_name,
    "editing_phone": on_editing_phone,
}


def register_handlers(bot: Bot) -> None:
    async def _safe(coro, message: Message) -> None:
        """Гарантирует ответ пользователю и лог ошибки, даже если backend недоступен
        или упал с непредвиденным исключением (сеть, не-JSON ответ и т.п.)."""
        try:
            await coro
        except Exception:
            log.exception("error handling command for vk user %s", message.from_id)
            await message.answer(t.GENERIC_ERROR, keyboard=kb.main_menu_kb())
            reset_session(message.from_id)

    @bot.on.message()
    async def handle_message(message: Message):
        text = (message.text or "").strip()
        session = get_session(message.from_id)

        try:
            await _ensure_registered(bot, message, session)
        except Exception:
            log.exception("registration failed for vk user %s", message.from_id)

        # Глобальные команды работают из любого шага диалога
        if text.lower() in ("начать", "start", "привет") and not session.get("greeted"):
            session["greeted"] = True
            await _safe(show_main_menu(message), message)
            return
        if text == t.CMD_CANCEL:
            reset_session(message.from_id)
            await _safe(show_main_menu(message), message)
            return
        if text == t.CMD_NEW_APPOINTMENT:
            _restart_flow(message, session)
            session = get_session(message.from_id)
            await _safe(start_booking(message, session), message)
            return
        if text == t.CMD_MY_APPOINTMENTS:
            _restart_flow(message, session)
            session = get_session(message.from_id)
            await _safe(show_my_appointments(message, session), message)
            return
        if text == t.CMD_MY_CARS:
            _restart_flow(message, session)
            session = get_session(message.from_id)
            await _safe(show_my_cars(message, session), message)
            return
        if text == t.CMD_WORK_HISTORY:
            _restart_flow(message, session)
            await _safe(show_work_history(message), message)
            return
        if text == t.CMD_PROFILE:
            _restart_flow(message, session)
            session = get_session(message.from_id)
            await _safe(show_profile(message, session), message)
            return
        if text == t.CMD_CONTACTS:
            await _safe(show_contacts(message), message)
            return

        step = session.get("step")
        handler = _STEP_HANDLERS.get(step)
        if handler:
            try:
                await handler(message, session, text)
            except Exception:
                log.exception("error handling step %s for vk user %s", step, message.from_id)
                await message.answer(t.GENERIC_ERROR, keyboard=kb.main_menu_kb())
                reset_session(message.from_id)
            return

        await show_main_menu(message)


def main() -> None:
    if not VK_GROUP_TOKEN:
        log.warning("VK_GROUP_TOKEN не задан - VK-бот не запущен. "
                   "Заполните VK_GROUP_TOKEN в .env и перезапустите контейнер.")
        while True:
            _time.sleep(3600)

    # aiohttp не читает HTTP_PROXY/HTTPS_PROXY сам по себе. Docker Desktop
    # проксирует исходящий трафик через http.docker.internal:3128, поэтому
    # явно включаем доверие к окружению — иначе polling VK висит без сети.
    http_client = AiohttpClient(trust_env=True)
    api = API(token=VK_GROUP_TOKEN, http_client=http_client)
    bot = Bot(api=api)
    register_handlers(bot)
    log.info("VK-бот Вмятый Элемент запускается...")

    backoff = 5
    while True:
        try:
            bot.run()
            break  # штатное завершение
        except Exception as e:
            log.error("Сбой соединения с VK (%s) - повтор через %s с",
                     e.__class__.__name__, backoff)
            _time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
