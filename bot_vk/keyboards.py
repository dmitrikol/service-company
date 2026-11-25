"""Сборка обычных (не inline) клавиатур VK — максимум 4 кнопки в ряду (лимит VK API)."""
from vkbottle import Keyboard, Text, KeyboardButtonColor

from texts import (
    CMD_NEW_APPOINTMENT, CMD_MY_APPOINTMENTS, CMD_CONTACTS, CMD_CANCEL,
    CMD_BACK, CMD_MORE_DATES, CMD_SKIP_PHONE, CMD_CONFIRM, CMD_YES_CANCEL,
    CMD_ADD_CAR, CMD_MY_CARS, CMD_WORK_HISTORY, CMD_PROFILE,
    CMD_EDIT_NAME, CMD_EDIT_PHONE,
)

MAX_PER_ROW = 4
VK_LABEL_LIMIT = 40


def _clip(label: str) -> str:
    """Страховка от VKAPIError_911 (VK отклоняет всю клавиатуру, если хоть одна
    подпись длиннее 40 символов). Основные места обрезают текст заранее сами
    (нужно, чтобы подпись кнопки совпадала с ключом словаря выбора в bot.py),
    это — запасной барьер."""
    if len(label) <= VK_LABEL_LIMIT:
        return label
    return label[:VK_LABEL_LIMIT - 1].rstrip() + "…"


def chunk(items: list[str], per_row: int) -> list[list[str]]:
    per_row = min(per_row, MAX_PER_ROW)
    return [items[i:i + per_row] for i in range(0, len(items), per_row)]


def _build(rows: list[list[str]]) -> str:
    kb = Keyboard(one_time=False, inline=False)
    for i, row in enumerate(rows):
        if i > 0:
            kb.row()
        for label in row:
            kb.add(Text(_clip(label)), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def main_menu_kb() -> str:
    return _build([
        [CMD_NEW_APPOINTMENT, CMD_MY_APPOINTMENTS],
        [CMD_MY_CARS, CMD_WORK_HISTORY],
        [CMD_PROFILE, CMD_CONTACTS],
    ])


def my_cars_kb() -> str:
    return _build([[CMD_ADD_CAR], [CMD_CANCEL]])


def profile_kb() -> str:
    return _build([[CMD_EDIT_NAME], [CMD_EDIT_PHONE], [CMD_CANCEL]])


def back_only_kb() -> str:
    return _build([[CMD_CANCEL]])


def cancel_only_kb() -> str:
    return _build([[CMD_CANCEL]])


def choices_kb(labels: list[str], per_row: int = 2, extra_rows: list[list[str]] | None = None) -> str:
    """Клавиатура выбора из списка подписей + доп. строки (например «Ещё» / «Отмена»)."""
    rows = chunk(labels, per_row)
    if extra_rows:
        rows += extra_rows
    return _build(rows)


def dates_kb(labels: list[str], has_more: bool) -> str:
    rows = chunk(labels, 3)
    tail = [CMD_MORE_DATES] if has_more else []
    tail.append(CMD_CANCEL)
    rows.append(tail)
    return _build(rows)


def times_kb(labels: list[str]) -> str:
    rows = chunk(labels, 4)
    rows.append([CMD_BACK, CMD_CANCEL])
    return _build(rows)


def phone_kb() -> str:
    return _build([[CMD_SKIP_PHONE], [CMD_CANCEL]])


def confirm_kb() -> str:
    return _build([[CMD_CONFIRM], [CMD_CANCEL]])


def add_car_kb() -> str:
    return _build([[CMD_CANCEL]])


def cars_kb(labels: list[str]) -> str:
    rows = chunk(labels, 2)
    rows.append([CMD_ADD_CAR])
    rows.append([CMD_CANCEL])
    return _build(rows)


def my_appointments_kb(labels: list[str]) -> str:
    rows = chunk(labels, 1)
    rows.append([CMD_BACK])
    return _build(rows) if rows else main_menu_kb()


def cancel_confirm_kb() -> str:
    return _build([[CMD_YES_CANCEL], [CMD_CANCEL]])
