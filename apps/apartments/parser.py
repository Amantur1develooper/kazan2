import re
from decimal import Decimal, InvalidOperation
from datetime import date


def _clean_name(raw) -> str:
    """Strip junk ФИО values like ',,,,,' or '.' → empty string."""
    s = str(raw).strip()
    cleaned = re.sub(r'[\s,.\-]+', '', s)
    return s if cleaned else ''


def _parse_amount(raw) -> Decimal:
    if raw is None or raw == '':
        return Decimal('0')
    s = str(raw).strip()
    s = re.sub(r'[\s\xa0]', '', s)   # non-breaking and regular spaces
    s = s.replace(',', '.')
    s = re.sub(r'\.(?=.*\.)', '', s) # remove all but last dot
    try:
        return Decimal(s).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _parse_date(raw) -> date | None:
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ('%d-%m-%Y', '%d.%m.%Y', '%Y-%m-%d'):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _parse_status(contract_type: str, client_name: str, paid: Decimal):
    """Return (is_sold, is_reserved, is_barter)."""
    t = contract_type.lower()
    if 'бартер' in t:
        return True, False, True
    if 'брон' in t:
        return False, True, False
    # ordinary or empty
    is_sold = bool(client_name) or paid > 0
    return is_sold, False, False


def parse_apartments_excel(path: str) -> list[dict]:
    """
    Parse apartment XLS/XLSX by header name (TZ section 6.2).
    Returns list of dicts ready for Apartment model.
    """
    suffix = path.lower().rsplit('.', 1)[-1]
    if suffix == 'xls':
        import xlrd
        wb = xlrd.open_workbook(path)
        sh = wb.sheet_by_index(0)
        headers = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]
        rows_raw = [
            [sh.cell_value(r, c) for c in range(sh.ncols)]
            for r in range(1, sh.nrows)
        ]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        sh = wb.active
        all_rows = list(sh.iter_rows(values_only=True))
        headers = [str(v).strip() if v is not None else '' for v in all_rows[0]]
        rows_raw = [list(r) for r in all_rows[1:]]

    def col(name):
        try:
            return headers.index(name)
        except ValueError:
            return None

    CI = {
        'num':          col('№'),
        'floor':        col('Этаж'),
        'apt_num':      col('Предварительный номер'),
        'rooms':        col('Количество комнат'),
        'area':         col('Общая площадь ориентировочно'),
        'deal_date':    col('Дата договора'),
        'client':       col('Ф.И.О.'),
        'price_m2':     col('Цена за 1 м.кв.'),
        'contract_sum': col('Сумма договора'),
        'paid':         col('Оплачено'),
        'remaining':    col('Остаток на оплату'),
        'phone':        col('Телефон'),
        'notes':        col('Примечание'),
        'contract_type':col('Тип сделки'),
        'curator':      col('Куратор ОП'),
    }

    def get(row, key):
        idx = CI.get(key)
        if idx is None or idx >= len(row):
            return ''
        v = row[idx]
        return '' if v is None else v

    results = []
    for row in rows_raw:
        apt_num_raw = get(row, 'apt_num')
        if not apt_num_raw:
            continue
        apt_num = str(apt_num_raw).strip()
        # strip text after '('
        apt_num = apt_num.split('(')[0].strip()
        if not apt_num:
            continue

        client_name = _clean_name(get(row, 'client'))
        phone_raw   = _clean_name(get(row, 'phone'))
        phone       = phone_raw if re.search(r'\d', phone_raw) else ''

        paid         = _parse_amount(get(row, 'paid'))
        contract_sum = _parse_amount(get(row, 'contract_sum'))
        remaining    = _parse_amount(get(row, 'remaining'))
        price_m2     = _parse_amount(get(row, 'price_m2'))

        # remaining fallback
        if remaining == 0 and contract_sum > 0:
            remaining = max(contract_sum - paid, Decimal('0'))

        contract_type = str(get(row, 'contract_type')).strip()
        is_sold, is_reserved, is_barter = _parse_status(contract_type, client_name, paid)

        try:
            floor = int(float(str(get(row, 'floor') or 1)))
        except (ValueError, TypeError):
            floor = 1

        try:
            rooms = int(float(str(get(row, 'rooms') or 1)))
        except (ValueError, TypeError):
            rooms = 1

        area = _parse_amount(get(row, 'area'))

        notes_parts = []
        note_raw = str(get(row, 'notes')).strip()
        note_clean = re.sub(r'^[\s,.\-]+$', '', note_raw)
        if note_clean and note_clean not in (',', '.', ',,,,'):
            notes_parts.append(note_clean)
        if phone:
            notes_parts.append(f'Тел: {phone}')

        results.append({
            'apartment_number':      apt_num,
            'floor':                 floor,
            'rooms':                 rooms,
            'area':                  area,
            'planned_price_per_m2':  price_m2,
            'fact_price_per_m2':     price_m2,
            'client_name':           client_name,
            'phone':                 phone,
            'deal_date':             _parse_date(get(row, 'deal_date')),
            'deal_amount_contract':  contract_sum,
            'deal_amount_paid':      paid,
            'deal_amount_remaining': remaining,
            'is_sold':               is_sold,
            'is_reserved':           is_reserved,
            'is_barter':             is_barter,
            'contract_type':         contract_type,
            'curator':               _clean_name(get(row, 'curator')),
            'notes':                 '\n'.join(notes_parts),
        })

    return results
