"""Тексты и подписи кнопок VK-бота (клиентский сценарий: запись на услуги)."""

# ─── Глобальные команды (работают из любого шага) ───
CMD_NEW_APPOINTMENT = "🔧 Записаться"
CMD_MY_APPOINTMENTS = "📋 Мои записи"
CMD_MY_CARS = "🚘 Мои авто"
CMD_WORK_HISTORY = "🧾 История работ"
CMD_PROFILE = "👤 Профиль"
CMD_CONTACTS = "📞 Контакты"
CMD_CANCEL = "❌ Отмена"
CMD_BACK = "⬅️ Назад"
CMD_MORE_DATES = "Ещё даты ▸"
CMD_SKIP_PHONE = "Пропустить"
CMD_CONFIRM = "✅ Подтвердить"
CMD_YES_CANCEL = "Да, отменить"
CMD_ADD_CAR = "➕ Добавить авто"
CMD_EDIT_NAME = "✏️ Изменить имя"
CMD_EDIT_PHONE = "✏️ Изменить телефон"

WELCOME = (
    "Здравствуйте! 👋 Это бот автосервиса «Service Company».\n\n"
    "Здесь можно записаться на услугу, посмотреть свои записи или узнать контакты.\n"
    "Выберите пункт на клавиатуре внизу 👇"
)

MAIN_MENU_HINT = "Выберите, что нужно сделать 👇"

NO_SERVICES = "Пока нет доступных услуг. Загляните позже."
CHOOSE_SERVICE = "Выберите услугу:"
UNKNOWN_CHOICE = "Не понял выбор — нажмите одну из кнопок на клавиатуре."

ENTER_CAR_FIRST = (
    "Для записи нужен автомобиль. У вас его ещё нет в системе — добавим?\n"
    "Напишите марку и модель одним сообщением, например: <BMW X5>"
)
CHOOSE_CAR = "Выберите автомобиль:"
WRONG_CAR_FORMAT = "Не понял. Напишите марку и модель через пробел, например: BMW X5"
CAR_ADD_FAILED = "❌ Не получилось добавить автомобиль. Попробуйте ещё раз."

CHOOSE_DATE = "Выберите дату записи:"
NO_DATES_AVAILABLE = "Свободных дат в ближайшее время не нашлось. Попробуйте позже."
CHOOSE_TIME = "Выберите время на {date}:"
NO_TIMES_AVAILABLE = "На этот день свободного времени не осталось. Выберите другую дату."

ASK_PHONE = (
    "Укажите номер телефона, чтобы мастер мог с вами связаться "
    "(или нажмите «Пропустить»):"
)

CONFIRM_APPOINTMENT = (
    "Проверьте, всё верно:\n\n"
    "🔧 Услуга: {service}\n"
    "🚘 Автомобиль: {car}\n"
    "🕐 Когда: {when}\n"
    "📞 Телефон: {phone}\n\n"
    "Подтвердить запись?"
)

APPOINTMENT_CREATED = "✅ Запись создана! Ждём вас {when}."
APPOINTMENT_FAILED = "❌ Не удалось создать запись: {detail}\nПопробуйте выбрать другое время."

MY_APPOINTMENTS_EMPTY = "У вас пока нет активных записей."
MY_APPOINTMENTS_TITLE = "Ваши записи:"


def appointment_line(a: dict) -> str:
    return f"🔧 {a['service']} · 🚘 {a['car']} · 🕐 {a['when']}"


CANCEL_CONFIRM = "Точно отменить запись «{service}» на {when}?"
APPOINTMENT_CANCELLED = "🗑 Запись отменена."
APPOINTMENT_CANCEL_FAILED = "❌ Не удалось отменить запись: {detail}"

CONTACTS_FAILED = "Не удалось загрузить контакты, попробуйте позже."

MY_CARS_TITLE = "Ваши автомобили:"
MY_CARS_EMPTY = "У вас пока нет добавленных автомобилей."


def car_line(c: dict) -> str:
    plate = f" · {c['plate_number']}" if c.get("plate_number") else ""
    return f"🚘 {c['brand']} {c['model']}{plate}"


WORK_HISTORY_TITLE = "История выполненных работ:"
WORK_HISTORY_EMPTY = "Пока нет завершённых работ по вашим автомобилям."


def work_line(w: dict) -> str:
    when = w.get("performed_at")
    when = when[:10] if when else "—"
    price = w.get("total_amount") if w.get("total_amount") is not None else w.get("actual_price")
    price_line = f" · {price}₽" if price is not None else ""
    return f"🧾 {when} · {w['service']} · {w['car']}{price_line}"


def profile_text(me: dict) -> str:
    name = me.get("name") or "—"
    phone = me.get("phone") or "—"
    return f"👤 Профиль\n\nИмя: {name}\nТелефон: {phone}"


ASK_NEW_NAME = "Введите новое имя:"
ASK_NEW_PHONE = "Введите новый номер телефона:"
PROFILE_UPDATED = "✅ Профиль обновлён."
PROFILE_UPDATE_FAILED = "❌ Не удалось обновить профиль: {detail}"

GENERIC_ERROR = "Что-то пошло не так. Попробуйте ещё раз или нажмите «Отмена»."
NOT_REGISTERED = "Не получилось вас найти в системе, попробуйте написать «Начать» ещё раз."
