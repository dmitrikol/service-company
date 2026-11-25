"""Сборка Excel-выгрузки журнала работ (история оказанных услуг).

Лист «История» — колонки: Дата | Услуга | Клиент | Ник VK | Телефон |
Цена | Комментарий (хронологически, старые сверху). Лист «Общее» — сводка по
годам и по месяцам: число работ и сумма по `actual_price` (как в шапке журнала
«N · 💵 X ₽»).

Вход — список словарей работ в форме `_work_dict` (backend/app/api/v1/admin.py).
"""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font

WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_RU = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")

HISTORY_HEADERS = ["Дата", "Услуга", "Клиент", "Ник VK", "Телефон", "Цена", "Комментарий"]
YEAR_HEADERS = ["Год", "Работ", "Сумма"]
MONTH_HEADERS = ["Год", "Месяц", "Работ", "Сумма"]


def _date_cell(performed_at: str | None) -> str:
    """«2026-08-15T10:00:00+00:00» -> «15.08.2026 Пт» (битое → как есть)."""
    if not performed_at:
        return "—"
    try:
        dt = datetime.fromisoformat(performed_at)
    except (ValueError, TypeError):
        return (performed_at or "")[:10] or "—"
    return f"{dt:%d.%m.%Y} {WEEKDAYS_SHORT[dt.weekday()]}"


def _money(amount) -> float:
    try:
        return float(amount or 0)
    except (ValueError, TypeError):
        return 0.0


def _num(value: float):
    """Целое без лишних нулей, дробное — с двумя знаками."""
    value = round(value, 2)
    return int(value) if value == int(value) else value


def _nick(username: str | None) -> str:
    """«ivan» -> «@ivan»; пусто/нет → «—»."""
    if not username:
        return "—"
    return f"@{username}"


def _styled_header(ws, row: int, headers: list[str]) -> None:
    for col, title in enumerate(headers, start=1):
        ws.cell(row=row, column=col, value=title).font = Font(bold=True)


def build_works_xlsx(rows: list[dict]) -> bytes:
    """Собирает книгу журнала работ и возвращает её байты (.xlsx)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "История"
    _styled_header(ws, 1, HISTORY_HEADERS)

    ordered = sorted(
        rows,
        key=lambda r: (r.get("performed_at") is None, r.get("performed_at") or ""),
    )
    for r in ordered:
        ws.append([
            _date_cell(r.get("performed_at")),
            r.get("service") or "—",
            r.get("client_name") or "—",
            _nick(r.get("client_vk_username")),
            r.get("client_phone") or "—",
            _num(_money(r.get("actual_price"))),
            r.get("master_comment") or "",
        ])
    for col, width in zip("ABCDEFG", (14, 32, 22, 18, 18, 12, 40)):
        ws.column_dimensions[col].width = width

    # ─── Общее: по годам и по месяцам ───
    by_year: dict[int, list] = {}
    by_month: dict[tuple[int, int], list] = {}
    for r in rows:
        s = r.get("performed_at")
        if not s:
            continue
        try:
            dt = datetime.fromisoformat(s)
        except (ValueError, TypeError):
            continue
        by_year.setdefault(dt.year, []).append(r)
        by_month.setdefault((dt.year, dt.month), []).append(r)

    ws2 = wb.create_sheet("Общее")
    row = 1
    ws2.cell(row=row, column=1, value="По годам").font = Font(bold=True, size=12)
    row += 1
    _styled_header(ws2, row, YEAR_HEADERS)
    row += 1
    for year in sorted(by_year):
        works = by_year[year]
        ws2.cell(row=row, column=1, value=year)
        ws2.cell(row=row, column=2, value=len(works))
        ws2.cell(row=row, column=3,
                 value=_num(sum(_money(r.get("actual_price")) for r in works)))
        row += 1

    row += 1  # пустая строка-разделитель
    ws2.cell(row=row, column=1, value="По месяцам").font = Font(bold=True, size=12)
    row += 1
    _styled_header(ws2, row, MONTH_HEADERS)
    row += 1
    for (year, month) in sorted(by_month):
        works = by_month[(year, month)]
        ws2.cell(row=row, column=1, value=year)
        ws2.cell(row=row, column=2, value=MONTHS_RU[month - 1])
        ws2.cell(row=row, column=3, value=len(works))
        ws2.cell(row=row, column=4,
                 value=_num(sum(_money(r.get("actual_price")) for r in works)))
        row += 1

    for col, width in zip("ABCD", (10, 16, 10, 14)):
        ws2.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
