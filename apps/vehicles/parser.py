"""
Parser for Склад Авто Excel template.

Columns (row 0 = header, row 1 = sub-header, data starts at row 2+):
  0: Дата
  1: Объект поступления
  2: Сумма Приход
  3: Сумма Расход
  4: Убыток  (calculated, skip)
  5: Назначение ухода
  6: Назначение авто
  7: Объект расхода
  8: Куда ушло
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation


def _to_decimal(value) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    s = str(value).strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    s = re.sub(r'[^\d.\-]', '', s)
    if not s or s in ('-', '.'):
        return Decimal('0')
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal('0')


def _parse_date(ws, r, c, datemode):
    import xlrd
    cell = ws.cell(r, c)
    if cell.ctype == xlrd.XL_CELL_DATE:
        t = xlrd.xldate_as_tuple(cell.value, datemode)
        try:
            return date(t[0], t[1], t[2])
        except ValueError:
            return None
    s = str(cell.value).strip()
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _str(v) -> str:
    if v is None:
        return ''
    s = str(v).strip()
    # remove trailing .0 from xlrd float strings
    if s.endswith('.0') and s[:-2].isdigit():
        return ''
    return s


def parse_vehicles_excel(filepath: str) -> list:
    """Parse Склад Авто Excel. Returns list of dicts."""
    import xlrd
    wb = xlrd.open_workbook(filepath)
    ws = wb.sheet_by_index(0)

    records = []
    for r in range(2, ws.nrows):  # skip header rows 0-1
        row_date = _parse_date(ws, r, 0, wb.datemode)
        if not row_date:
            continue
        vehicle_name = _str(ws.cell_value(r, 6)) if ws.ncols > 6 else ''
        if not vehicle_name:
            continue

        records.append({
            'date':         row_date,
            'source_text':  _str(ws.cell_value(r, 1)) if ws.ncols > 1 else '',
            'amount_in':    _to_decimal(ws.cell_value(r, 2) if ws.ncols > 2 else None),
            'amount_out':   _to_decimal(ws.cell_value(r, 3) if ws.ncols > 3 else None),
            'counterparty': _str(ws.cell_value(r, 5)) if ws.ncols > 5 else '',
            'vehicle_name': vehicle_name,
            'target_text':  _str(ws.cell_value(r, 7)) if ws.ncols > 7 else '',
            'purpose':      _str(ws.cell_value(r, 8)) if ws.ncols > 8 else '',
        })
    return records
