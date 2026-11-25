"""Сборка Excel-выгрузки по одной услуге: кто и когда заплатил какую цену.

Лист «Оплаты» — колонки: Дата | Клиент | Ник VK | Телефон |
Автомобиль | Цена | Итого | Комментарий (хронологически, старые сверху) —
фактические суммы по каждому выполненному заказу этой услуги.

Лист «Изменения цены» — колонки: Дата | Цена «от» (старые сверху) —
история изменения базовой (прайсовой) цены услуги, отдельно от того, что
реально платили клиенты (могли быть скидки/наценки по конкретному заказу).
"""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font

from app.services.works_export import _date_cell, _money, _num, _nick, _styled_header

PAYMENTS_HEADERS = ["Дата", "Клиент", "Ник VK", "Телефон",
                    "Автомобиль", "Цена", "Итого", "Комментарий"]
PRICE_HEADERS = ["Дата изменения", "Цена «от»"]


def build_service_export_xlsx(service: dict, works: list[dict], price_history: list[dict]) -> bytes:
    """Собирает книгу «Оплаты + Изменения цены» по одной услуге и возвращает байты (.xlsx)."""
    wb = Workbook()

    ws = wb.active
    ws.title = "Оплаты"
    ws.cell(row=1, column=1, value=f"Услуга: {service.get('name') or '—'}").font = Font(bold=True, size=12)
    ws.cell(row=2, column=1,
            value=f"Текущая цена «от»: {_num(_money(service.get('price_from')))} ₽").font = Font(italic=True)
    _styled_header(ws, 4, PAYMENTS_HEADERS)

    ordered = sorted(
        works,
        key=lambda r: (r.get("performed_at") is None, r.get("performed_at") or ""),
    )
    row = 5
    for r in ordered:
        ws.append([
            _date_cell(r.get("performed_at")),
            r.get("client_name") or "—",
            _nick(r.get("client_vk_username")),
            r.get("client_phone") or "—",
            r.get("car") or "—",
            _num(_money(r.get("actual_price"))),
            _num(_money(r.get("total_amount"))),
            r.get("master_comment") or "",
        ])
        row += 1
    if not ordered:
        ws.cell(row=row, column=1, value="Пока нет ни одной выполненной работы по этой услуге.")

    for col, width in zip("ABCDEFGH", (14, 22, 18, 18, 20, 12, 12, 40)):
        ws.column_dimensions[col].width = width

    # ─── Итого по оплатам ───
    if ordered:
        total_row = 4 + len(ordered) + 2
        ws.cell(row=total_row, column=1, value="Итого работ:").font = Font(bold=True)
        ws.cell(row=total_row, column=2, value=len(ordered)).font = Font(bold=True)
        ws.cell(row=total_row, column=7, value="Сумма:").font = Font(bold=True)
        ws.cell(row=total_row, column=8,
                value=_num(sum(_money(r.get("actual_price")) for r in ordered))).font = Font(bold=True)

    # ─── Лист «Изменения цены» ───
    ws2 = wb.create_sheet("Изменения цены")
    _styled_header(ws2, 1, PRICE_HEADERS)
    price_rows = sorted(price_history, key=lambda p: p.get("changed_at") or "")
    for p in price_rows:
        ws2.append([_date_cell(p.get("changed_at")), _num(_money(p.get("price_from")))])
    if not price_rows:
        ws2.cell(row=2, column=1, value="Изменений базовой цены ещё не было.")
    for col, width in zip("AB", (18, 14)):
        ws2.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
