"""
Estimate Excel parser.

Excel format (Сметный план блока):
  Col 0:  № (section code: int for top-level, "X.Y" or "X.Y.Z" for sub-levels)
  Col 1:  Наименование
  Col 5:  Единица измерения
  Col 6:  Количество
  Col 9:  Единица стоимости РАБОТ (unit labor price)
  Col 10: Общая стоимость РАБОТ (total labor)
  Col 12: Единица стоимости МАТЕРИАЛОВ (unit material price)
  Col 13: Общая цена МАТЕРИАЛОВ (total material)
  Col 15: ИТОГО СТОИМОСТИ (= col10 + col13)

Section detection:
  - No qty AND no unit_price → section header (sub-total row)
  - Has qty OR unit_price → leaf item
"""

import re
from decimal import Decimal, InvalidOperation


def _dec(v) -> Decimal:
    if v is None:
        return Decimal('0')
    s = str(v).strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    s = re.sub(r'[^\d.\-]', '', s)
    if not s or s in ('-', '.'):
        return Decimal('0')
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal('0')


def _str(v) -> str:
    if v is None:
        return ''
    return str(v).strip()


def _code_str(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    s = str(v).strip()
    # Normalize: replace commas used as decimal separators with dots, strip trailing separators
    s = s.replace(',', '.').strip('.')
    # Collapse consecutive dots (e.g. "7..9" → "7.9")
    while '..' in s:
        s = s.replace('..', '.')
    return s


def _code_depth(code: str) -> int:
    return code.count('.')


def _code_parent(code: str) -> str:
    idx = code.rfind('.')
    return code[:idx] if idx >= 0 else ''


def parse_estimate_excel(filepath: str) -> dict:
    """
    Parse estimate Excel file. Returns dict with:
      {
        'title': str,
        'rows': [
          {
            'code': str,       # e.g. "5", "5.1", "4.1.2"
            'name': str,
            'unit': str,
            'quantity': Decimal,
            'unit_price': Decimal,   # material unit price if exists, else labor
            'total_amount': Decimal, # col15 (labor + material)
            'is_section': bool,      # True = sub-total row, False = leaf item
            'depth': int,            # 0 = top, 1 = sub, 2 = sub-sub
            'note': str,
          }
        ]
      }
    """
    ext = filepath.rsplit('.', 1)[-1].lower()

    if ext == 'xls':
        import xlrd
        wb = xlrd.open_workbook(filepath)
        ws = wb.sheet_by_index(0)
        raw_rows = [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = list(wb.worksheets)[0]
        raw_rows = [list(row) for row in ws.iter_rows(values_only=True)]
        wb.close()

    title = ''
    rows = []

    for raw in raw_rows:
        if len(raw) < 2:
            continue
        col0 = raw[0] if len(raw) > 0 else None
        col1 = raw[1] if len(raw) > 1 else None

        if col0 is None:
            # Might be a title row
            if not title and col1:
                s = _str(col1)
                if len(s) > 5 and not any(h in s.lower() for h in ['наименован', 'единиц', '№']):
                    title = s
            continue

        # Skip header/number rows
        if _str(col0).lower() in ('№', 'n', '1', '2', '3') and _str(col1).lower() in ('наименование', 'наименование ', '2'):
            continue

        code = _code_str(col0)
        if not code:
            continue

        # Validate code format: must be numeric or "X.Y" pattern
        parts = code.split('.')
        if not all(p.isdigit() for p in parts if p):
            continue

        name = _str(col1)
        if not name:
            continue

        unit = _str(raw[5]) if len(raw) > 5 else ''
        qty_raw = raw[6] if len(raw) > 6 else None
        note_raw = raw[7] if len(raw) > 7 else None

        unit_labor_raw = raw[9] if len(raw) > 9 else None
        total_labor_raw = raw[10] if len(raw) > 10 else None
        unit_mat_raw = raw[12] if len(raw) > 12 else None
        total_mat_raw = raw[13] if len(raw) > 13 else None
        total_raw = raw[15] if len(raw) > 15 else None

        qty = _dec(qty_raw) if (qty_raw is not None and not isinstance(qty_raw, str)) else Decimal('0')
        unit_labor = _dec(unit_labor_raw)
        total_labor = _dec(total_labor_raw)
        unit_mat = _dec(unit_mat_raw)
        total_mat = _dec(total_mat_raw)
        total = _dec(total_raw)

        if total == 0:
            total = total_labor + total_mat

        # Determine unit_price: prefer material, fallback to labor
        unit_price = unit_mat if unit_mat > 0 else unit_labor

        # Is this a section or a leaf item?
        has_price = unit_price > 0 or total > 0
        has_qty = qty > 0
        is_section = not has_qty and (not unit_price or (unit_labor == 0 and unit_mat == 0))

        note = _str(note_raw) if isinstance(note_raw, str) else ''

        rows.append({
            'code': code,
            'name': name,
            'unit': unit,
            'quantity': qty,
            'unit_price': unit_price,
            'total_amount': total,
            'is_section': is_section,
            'depth': _code_depth(code),
            'note': note,
        })

    return {'title': title, 'rows': rows}


def apply_estimate_import(estimate, parsed_data, source_file=''):
    """
    Apply parsed estimate data. Saves a version snapshot and change log before replacing.

    Returns stats dict: sections, items, matched, added, updated, removed.
    """
    from .models import (
        EstimateSection, EstimateItem, Nomenclature, NomenclatureAlias,
        EstimateVersion, EstimateChangeLog,
    )
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    from django.db.models import Value

    # ── 1. Snapshot existing items before clearing ────────────────────────────
    total_before = estimate.total_amount
    old_items = {}  # code → {name, quantity, unit_price, total_amount}
    for item in EstimateItem.objects.filter(section__estimate=estimate):
        key = item.code or item.name.lower()
        old_items[key] = {
            'name': item.name,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_amount': item.total_amount,
        }

    # ── 2. Clear and re-import (resets all is_modified flags) ────────────────
    estimate.sections.all().delete()

    rows = parsed_data.get('rows', [])
    stats = {'sections': 0, 'items': 0, 'matched': 0}

    nom_by_name = {n.name.lower(): n for n in Nomenclature.objects.filter(is_active=True)}
    nom_by_alias = {a.alias_name.lower(): a.nomenclature for a in NomenclatureAlias.objects.select_related('nomenclature')}

    section_map = {}

    for order_idx, row in enumerate(rows):
        code = row['code']
        name = row['name']
        is_section = row['is_section']

        parent_code = _code_parent(code)
        parent = section_map.get(parent_code) if parent_code else None

        if is_section or (row['total_amount'] == 0 and row['quantity'] == 0):
            section = EstimateSection.objects.create(
                estimate=estimate,
                parent=parent,
                name=name,
                code=code,
                order=order_idx,
                total_amount=row['total_amount'],
            )
            section_map[code] = section
            stats['sections'] += 1
        else:
            if parent is None:
                parent_section = EstimateSection.objects.create(
                    estimate=estimate,
                    parent=None,
                    name=name,
                    code=code,
                    order=order_idx,
                    total_amount=row['total_amount'],
                )
                section_map[code] = parent_section
                stats['sections'] += 1
                continue

            name_lower = name.lower()
            nom = nom_by_alias.get(name_lower) or nom_by_name.get(name_lower)

            block_id = estimate.block_id
            # Include name to disambiguate items sharing the same code in one section
            sk = f'{block_id}:{code}:{name[:60]}' if code else f'{block_id}:{name[:80]}'

            EstimateItem.objects.create(
                section=parent,
                nomenclature=nom,
                code=code,
                name=name,
                unit=row['unit'],
                quantity=row['quantity'],
                unit_price=row['unit_price'],
                total_amount=row['total_amount'],
                note=row['note'],
                order=order_idx,
                stable_key=sk,
            )
            stats['items'] += 1
            if nom:
                stats['matched'] += 1

    # Recalculate totals
    all_sections = list(estimate.sections.all().order_by('-code'))
    for sec in all_sections:
        if not sec.children.exists():
            items_total = sec.items.aggregate(
                t=Coalesce(Sum('total_amount'), Value(Decimal('0')))
            )['t']
            if sec.total_amount == 0:
                sec.total_amount = items_total
                sec.save(update_fields=['total_amount'])

    for sec in estimate.sections.filter(parent__isnull=True).order_by('code'):
        if sec.total_amount == 0:
            _recalc_section(sec)

    estimate.recalculate_total()
    total_after = estimate.total_amount

    # ── 2.5 Add «Прочие расходы» subsection to each top-level section ────────
    _add_misc_expense_sections(estimate)

    # ── 2.6 Auto-create Stages in the block for each top-level section ────────
    _sync_stages_from_estimate(estimate)

    # ── 3. Build new items snapshot and compare ───────────────────────────────
    new_items = {}
    for item in EstimateItem.objects.filter(section__estimate=estimate):
        key = item.code or item.name.lower()
        new_items[key] = {
            'name': item.name,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_amount': item.total_amount,
        }

    change_logs = []
    added = updated = removed = 0

    # Added or updated
    for key, new in new_items.items():
        if key not in old_items:
            change_logs.append(EstimateChangeLog(
                action='added',
                item_code=key if key != new['name'].lower() else '',
                item_name=new['name'],
                field_name='total_amount',
                old_value='',
                new_value=_fmt(new['total_amount']),
            ))
            added += 1
        else:
            old = old_items[key]
            diffs = []
            for field, label in [('total_amount', 'Сумма'), ('unit_price', 'Цена'), ('quantity', 'Кол-во')]:
                if old[field] != new[field]:
                    diffs.append((field, label, old[field], new[field]))
            if diffs:
                for field, label, ov, nv in diffs:
                    change_logs.append(EstimateChangeLog(
                        action='updated',
                        item_code=key if key != new['name'].lower() else '',
                        item_name=new['name'],
                        field_name=label,
                        old_value=_fmt(ov),
                        new_value=_fmt(nv),
                    ))
                updated += 1

    # Removed
    for key, old in old_items.items():
        if key not in new_items:
            change_logs.append(EstimateChangeLog(
                action='removed',
                item_code=key if key != old['name'].lower() else '',
                item_name=old['name'],
                field_name='total_amount',
                old_value=_fmt(old['total_amount']),
                new_value='',
            ))
            removed += 1

    # ── 4. Save version record ────────────────────────────────────────────────
    is_first_import = not old_items  # no history before
    version = EstimateVersion.objects.create(
        estimate=estimate,
        source_file=source_file,
        total_before=total_before,
        total_after=total_after,
        sections_count=stats['sections'],
        items_count=stats['items'],
        items_added=added,
        items_updated=updated,
        items_removed=removed,
    )
    for log in change_logs:
        log.version = version
    EstimateChangeLog.objects.bulk_create(change_logs)

    stats.update({'added': added, 'updated': updated, 'removed': removed,
                  'version_id': version.pk, 'is_first_import': is_first_import})
    return stats


def _add_misc_expense_sections(estimate):
    """
    Add a 'Прочие расходы' subsection to each top-level section that doesn't have one.
    Code is automatically assigned as next numeric sibling (e.g. if last child is 3.8 → 3.9).
    """
    from .models import EstimateSection

    top_sections = list(estimate.sections.filter(parent__isnull=True).order_by('code'))

    for sec in top_sections:
        # Skip if already has a "Прочие расходы" child
        if sec.children.filter(name__icontains='прочие').exists():
            continue

        children = list(sec.children.order_by('code'))

        # Determine next sub-code number
        last_num = 0
        for child in children:
            parts = child.code.split('.')
            if len(parts) >= 2:
                try:
                    last_num = max(last_num, int(parts[-1]))
                except ValueError:
                    pass
        new_num = last_num + 1

        # Determine order: place after all existing children
        max_order = max((c.order for c in children), default=0)

        EstimateSection.objects.create(
            estimate=estimate,
            parent=sec,
            name='Прочие расходы',
            code=f'{sec.code}.{new_num}',
            order=max_order + 1,
            total_amount=Decimal('0'),
        )


def _fmt(value) -> str:
    try:
        return f'{float(value):,.0f}'.replace(',', ' ')
    except Exception:
        return str(value)


def _sync_stages_from_estimate(estimate):
    """
    For each top-level EstimateSection create (or update) a matching Stage in the block.
    Stages are matched by name. New stages are created; existing ones get planned_expenses updated.
    Floors are never touched — those are created manually.
    """
    from apps.projects.models import Stage

    top_sections = list(
        estimate.sections.filter(parent__isnull=True).order_by('order', 'code')
    )

    existing_stages = {s.name: s for s in Stage.objects.filter(block=estimate.block)}

    for idx, sec in enumerate(top_sections):
        label = f'{sec.code} {sec.name}'.strip()
        if label in existing_stages:
            stage = existing_stages[label]
            if stage.planned_expenses != sec.total_amount:
                stage.planned_expenses = sec.total_amount
                stage.save(update_fields=['planned_expenses'])
        else:
            Stage.objects.create(
                block=estimate.block,
                name=label,
                planned_expenses=sec.total_amount,
                order=idx,
            )


def _recalc_section(section):
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    from django.db.models import Value

    for child in section.children.all():
        if child.total_amount == 0:
            _recalc_section(child)

    items_total = section.items.aggregate(
        t=Coalesce(Sum('total_amount'), Value(Decimal('0')))
    )['t']
    children_total = section.children.aggregate(
        t=Coalesce(Sum('total_amount'), Value(Decimal('0')))
    )['t']
    new_total = items_total + children_total
    if new_total != section.total_amount:
        section.total_amount = new_total
        section.save(update_fields=['total_amount'])
