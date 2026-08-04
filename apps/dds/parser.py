"""
DDS (ДДС) Excel parser for 1С cash flow export.

Expected columns (row 0 = header):
  0: Дата
  1: Банк / Касса
  2: Операция
  3: Сумма            (positive = income, negative = expense, empty for transfers)
  4: Сумма перемещения (for transfers)
  5: Откуда / куда
  6: Касса / счет
  7: Объект
  8: Назначение
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


def _parse_date_cell(ws, r, c, datemode):
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
    return str(v).strip()


def parse_dds_excel(filepath: str) -> list:
    """Parse 1С ДДС Excel file. Returns list of record dicts."""
    import xlrd
    wb = xlrd.open_workbook(filepath)
    ws = wb.sheet_by_index(0)

    records = []
    for r in range(1, ws.nrows):  # skip header row 0
        row_date = _parse_date_cell(ws, r, 0, wb.datemode)
        if not row_date:
            continue

        bank_or_cash = _str(ws.cell_value(r, 1))
        op_type = _str(ws.cell_value(r, 2))
        if not op_type:
            continue

        amount_raw = _to_decimal(ws.cell_value(r, 3) if ws.ncols > 3 else None)
        transfer_raw = _to_decimal(ws.cell_value(r, 4) if ws.ncols > 4 else None)
        counterparty = _str(ws.cell_value(r, 5) if ws.ncols > 5 else None)
        account_name = _str(ws.cell_value(r, 6) if ws.ncols > 6 else None)
        object_ref = _str(ws.cell_value(r, 7) if ws.ncols > 7 else None)
        description = _str(ws.cell_value(r, 8) if ws.ncols > 8 else None)

        # Determine direction
        op_lower = op_type.lower()
        if 'перемещение' in op_lower or (transfer_raw != 0 and amount_raw == 0):
            direction = 'transfer'
            amount = abs(transfer_raw)
        elif amount_raw > 0:
            direction = 'in'
            amount = amount_raw
        elif amount_raw < 0:
            direction = 'out'
            amount = abs(amount_raw)
        else:
            continue  # zero amount, skip

        records.append({
            'operation_date': row_date,
            'bank_or_cash': bank_or_cash,
            'operation_type': op_type,
            'direction': direction,
            'amount': amount,
            'transfer_amount': abs(transfer_raw),
            'counterparty': counterparty,
            'account_name': account_name,
            'object_ref': object_ref,
            'description': description,
        })

    return records


def auto_match_block(object_ref: str, blocks) -> object:
    """Try to find a Block whose name appears in object_ref string."""
    if not object_ref:
        return None
    obj_lower = object_ref.lower()
    for block in sorted(blocks, key=lambda b: len(b.name), reverse=True):
        if block.name.lower() in obj_lower:
            return block
    return None


def apply_dds_import(residential_complex, records: list, dds_import) -> dict:
    """
    Persist parsed DDS records to the database.
    Auto-creates CashAccount records per unique account_name.
    Auto-matches blocks by object_ref string.
    Returns stats dict.
    """
    from .models import CashAccount, CashFlowRecord
    from apps.projects.models import Block

    # Guard: skip if already applied
    if dds_import and CashFlowRecord.objects.filter(source_import=dds_import).exists():
        return {'created': 0, 'errors': 0}

    # Pre-load accounts cache: name → CashAccount
    account_cache = {}
    for acc in CashAccount.objects.filter(residential_complex=residential_complex):
        account_cache[acc.name] = acc

    # Pre-load all blocks for auto-matching
    all_blocks = list(Block.objects.filter(
        residential_complex=residential_complex
    ).select_related('residential_complex'))

    stats = {'created': 0, 'errors': 0}
    to_create = []

    for item in records:
        try:
            acc_name = item.get('account_name', '')
            if acc_name and acc_name not in account_cache:
                acc_type = 'bank' if 'банк' in item.get('bank_or_cash', '').lower() or any(
                    c.isdigit() for c in acc_name[:6]
                ) else 'cash'
                acc = CashAccount.objects.create(
                    name=acc_name,
                    account_type=acc_type,
                    residential_complex=residential_complex,
                )
                account_cache[acc_name] = acc
            account = account_cache.get(acc_name)

            block = auto_match_block(item.get('object_ref', ''), all_blocks)

            op_date = item['operation_date']
            if hasattr(op_date, 'isoformat'):
                pass  # already a date object
            else:
                from datetime import datetime
                op_date = datetime.strptime(op_date, '%Y-%m-%d').date()

            to_create.append(CashFlowRecord(
                operation_date=op_date,
                bank_or_cash=item.get('bank_or_cash', ''),
                operation_type=item.get('operation_type', ''),
                direction=item.get('direction', 'out'),
                amount=item.get('amount', 0),
                transfer_amount=item.get('transfer_amount', 0),
                counterparty=item.get('counterparty', ''),
                account_name=acc_name,
                object_ref=item.get('object_ref', ''),
                description=item.get('description', ''),
                account=account,
                block=block,
                source_import=dds_import,
            ))
            stats['created'] += 1
        except Exception:
            stats['errors'] += 1

    CashFlowRecord.objects.bulk_create(to_create)
    return stats
