"""Сборка Excel-выгрузки базы клиентов и их машин (бэкап/миграция).

Лист «Клиенты» — колонки: Имя | Телефон | VK | Записей | Создан.
Лист «Машины» — колонки: Клиент | Марка | Модель | Госномер | VIN.
"""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font

CLIENT_HEADERS = ["Имя", "Телефон", "VK", "Записей", "Создан"]
CAR_HEADERS = ["Клиент", "Марка", "Модель", "Госномер", "VIN"]


def _nick(username: str | None) -> str:
    return f"@{username}" if username else "—"


def _date_cell(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso[:10] if iso else "—"
    return f"{dt:%d.%m.%Y}"


def _styled_header(ws, row: int, headers: list[str]) -> None:
    for col, title in enumerate(headers, start=1):
        ws.cell(row=row, column=col, value=title).font = Font(bold=True)


def build_clients_xlsx(clients: list[dict], cars: list[dict]) -> bytes:
    """Собирает книгу «Клиенты + Машины» и возвращает её байты (.xlsx)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Клиенты"
    _styled_header(ws, 1, CLIENT_HEADERS)
    for c in clients:
        ws.append([
            c.get("name") or "—",
            c.get("phone") or "—",
            _nick(c.get("vk_username")) if c.get("vk_username") else
            (c.get("vk_external_id") or "—"),
            c.get("appointments_count") or 0,
            _date_cell(c.get("created_at")),
        ])
    for col, width in zip("ABCDE", (26, 18, 22, 10, 14)):
        ws.column_dimensions[col].width = width

    ws2 = wb.create_sheet("Машины")
    _styled_header(ws2, 1, CAR_HEADERS)
    for car in cars:
        ws2.append([
            car.get("client_name") or "—",
            car.get("brand") or "—",
            car.get("model") or "—",
            car.get("plate_number") or "—",
            car.get("vin") or "—",
        ])
    for col, width in zip("ABCDE", (26, 16, 16, 16, 20)):
        ws2.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
