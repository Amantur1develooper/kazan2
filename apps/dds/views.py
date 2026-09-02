import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.db.models import Value
from django.utils import timezone

from apps.projects.models import ResidentialComplex, Block
from .models import CashAccount, DDSImport, CashFlowRecord
from .forms import DDSImportForm
from .parser import parse_dds_excel, apply_dds_import


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_item_choices_for_dds(blocks):
    """Build [{type,label,id}] grouped by block → section for <select>."""
    from apps.estimates.models import EstimateItem
    choices = []
    for block in blocks:
        try:
            items = list(
                EstimateItem.objects.filter(section__estimate__block=block)
                .select_related('section')
                .order_by('section__code', 'order')
            )
            if not items:
                continue
            choices.append({'type': 'optgroup', 'label': f'Блок {block.name}'})
            cur_sec = None
            for item in items:
                sec_label = f'{item.section.code} {item.section.name}'.strip()
                if sec_label != cur_sec:
                    choices.append({'type': 'optgroup', 'label': f'  {sec_label}'})
                    cur_sec = sec_label
                label = f'{item.code} {item.name}'.strip() if item.code else item.name
                choices.append({'type': 'option', 'id': item.pk, 'label': label})
        except Exception:
            continue
    return choices


# ── Import ────────────────────────────────────────────────────────────────────

def dds_import_upload(request):
    """Step 1: select ЖК and upload file."""
    if request.method == 'POST':
        form = DDSImportForm(request.POST, request.FILES)
        if form.is_valid():
            rc = form.cleaned_data['residential_complex']
            block = form.cleaned_data.get('block')
            uploaded = request.FILES['file']

            dds_import = DDSImport.objects.create(
                file=uploaded,
                original_filename=uploaded.name,
                residential_complex=rc,
                block=block,
                status='pending',
            )

            try:
                records = parse_dds_excel(dds_import.file.path)
                # Store preview in session (first 30 rows, JSON-safe)
                preview = []
                for rec in records[:30]:
                    preview.append({
                        'operation_date': rec['operation_date'].isoformat(),
                        'bank_or_cash': rec['bank_or_cash'],
                        'operation_type': rec['operation_type'],
                        'direction': rec['direction'],
                        'amount': float(rec['amount']),
                        'counterparty': rec['counterparty'],
                        'account_name': rec['account_name'],
                        'object_ref': rec['object_ref'],
                        'description': rec['description'],
                    })
                request.session['dds_preview'] = preview
                request.session['dds_total'] = len(records)
                request.session['dds_import_id'] = dds_import.pk
                return redirect('dds_import_preview', pk=dds_import.pk)
            except Exception as e:
                dds_import.status = 'error'
                dds_import.error_message = str(e)
                dds_import.save()
                messages.error(request, f'Ошибка чтения файла: {e}')
                return redirect('dds_import_upload')
    else:
        form = DDSImportForm()

    # Build RC→blocks mapping for JS filtering
    import json as _json
    all_blocks = Block.objects.select_related('residential_complex').order_by('name')
    blocks_by_rc = {}
    for blk in all_blocks:
        rc_id = str(blk.residential_complex_id)
        blocks_by_rc.setdefault(rc_id, []).append({'id': blk.pk, 'name': blk.name})
    blocks_by_rc_json = _json.dumps(blocks_by_rc, ensure_ascii=False)

    return render(request, 'dds/import_upload.html', {
        'form': form,
        'blocks_by_rc_json': blocks_by_rc_json,
    })


def dds_import_preview(request, pk):
    """Step 2: preview parsed records, then apply."""
    dds_import = get_object_or_404(
        DDSImport.objects.select_related('residential_complex'), pk=pk
    )

    preview = request.session.get('dds_preview', [])
    total = request.session.get('dds_total', 0)

    if not preview:
        try:
            records = parse_dds_excel(dds_import.file.path)
            total = len(records)
            preview = [
                {
                    'operation_date': r['operation_date'].isoformat(),
                    'operation_type': r['operation_type'],
                    'direction': r['direction'],
                    'amount': float(r['amount']),
                    'account_name': r['account_name'],
                    'object_ref': r['object_ref'],
                    'description': r['description'],
                }
                for r in records[:30]
            ]
        except Exception as e:
            messages.error(request, f'Ошибка предпросмотра: {e}')
            return redirect('dds_import_upload')

    # Stats from preview
    income_preview = sum(r['amount'] for r in preview if r['direction'] == 'in')
    expense_preview = sum(r['amount'] for r in preview if r['direction'] == 'out')
    transfer_preview = sum(r['amount'] for r in preview if r['direction'] == 'transfer')

    if request.method == 'POST':
        if dds_import.status == 'completed':
            messages.warning(request, 'Этот файл уже был импортирован.')
            return redirect('dds_distribute', pk=pk)

        dds_import.status = 'processing'
        dds_import.save(update_fields=['status'])

        try:
            records = parse_dds_excel(dds_import.file.path)
            stats = apply_dds_import(
                dds_import.residential_complex, records, dds_import,
                default_block=dds_import.block,
            )
            dds_import.rows_total = len(records)
            dds_import.rows_processed = stats['created']
            dds_import.rows_error = stats['errors']
            dds_import.status = 'completed'
            dds_import.processed_at = timezone.now()
            dds_import.save()
            messages.success(request, f'Импортировано {stats["created"]} записей.')
        except Exception as e:
            dds_import.status = 'error'
            dds_import.error_message = str(e)
            dds_import.save()
            messages.error(request, f'Ошибка импорта: {e}')
            return redirect('dds_import_upload')

        return redirect('dds_distribute', pk=pk)

    return render(request, 'dds/import_preview.html', {
        'dds_import': dds_import,
        'preview': preview,
        'total': total,
        'income_preview': income_preview,
        'expense_preview': expense_preview,
        'transfer_preview': transfer_preview,
    })


def dds_distribute(request, pk):
    """Step 3: link records to blocks and estimate items. Shows only unlinked, paginated."""
    dds_import = get_object_or_404(
        DDSImport.objects.select_related('residential_complex'), pk=pk
    )
    rc = dds_import.residential_complex

    all_blocks = list(Block.objects.filter(residential_complex=rc).order_by('name'))

    # Totals (cheap counts, no full fetch)
    total        = dds_import.records.count()
    linked_blocks = dds_import.records.filter(block__isnull=False).count()
    unlinked     = total - linked_blocks

    # If everything is linked — skip straight to accounts
    if unlinked == 0 and request.method != 'POST':
        messages.success(request, 'Все записи уже привязаны к блокам.')
        first_account = CashAccount.objects.filter(residential_complex=rc).first()
        if first_account:
            return redirect('dds_account_detail', pk=first_account.pk)
        return redirect('dds_account_list')

    # Pagination — only unlinked records, 150 per page
    PER_PAGE = 150
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except ValueError:
        page = 1
    offset = (page - 1) * PER_PAGE

    unlinked_qs = (
        dds_import.records
        .filter(block__isnull=True)
        .select_related('block', 'estimate_item', 'account')
        .order_by('direction', 'operation_date')
    )
    unlinked_count = unlinked_qs.count()
    records = list(unlinked_qs[offset: offset + PER_PAGE])
    total_pages = max(1, (unlinked_count + PER_PAGE - 1) // PER_PAGE)

    # Estimate item choices — only for blocks relevant to this import
    from apps.estimates.models import EstimateItem
    relevant_blocks = [dds_import.block] if dds_import.block else all_blocks
    all_items = list(
        EstimateItem.objects.filter(section__estimate__block__in=relevant_blocks)
        .select_related('section__estimate__block')
        .order_by('section__estimate__block__name', 'section__code', 'order')
    )
    item_choices = []
    cur_block = None
    for item in all_items:
        blk_label = f'Блок {item.section.estimate.block.name}'
        if blk_label != cur_block:
            item_choices.append({'type': 'optgroup', 'label': blk_label})
            cur_block = blk_label
        label = f'{item.code} {item.name}'.strip() if item.code else item.name
        item_choices.append({'type': 'option', 'id': item.pk, 'label': label})

    if request.method == 'POST':
        saved = 0
        pks = [r.pk for r in records]
        rec_map = {r.pk: r for r in records}
        for rec_pk in pks:
            rec = rec_map[rec_pk]
            block_val = request.POST.get(f'block_{rec_pk}', '').strip()
            item_val  = request.POST.get(f'item_{rec_pk}', '').strip()
            changed = False

            if block_val and block_val.isdigit():
                new_block = next((b for b in all_blocks if b.pk == int(block_val)), None)
                if new_block and rec.block_id != new_block.pk:
                    rec.block = new_block
                    changed = True
            elif block_val == '' and rec.block_id:
                rec.block = None
                changed = True

            if item_val and item_val.isdigit():
                item_pk = int(item_val)
                if rec.estimate_item_id != item_pk:
                    rec.estimate_item_id = item_pk
                    changed = True
            elif item_val == '' and rec.estimate_item_id:
                rec.estimate_item = None
                changed = True

            if changed:
                rec.save(update_fields=['block', 'estimate_item'])
                saved += 1

        messages.success(request, f'Сохранено: {saved} записей.')
        next_page = page if saved == 0 else page  # stay on same page, unlinked shrinks
        return redirect(f"{request.path}?page=1")

    return render(request, 'dds/distribute.html', {
        'dds_import': dds_import,
        'records': records,
        'all_blocks': all_blocks,
        'item_choices': item_choices,
        'total': total,
        'linked_blocks': linked_blocks,
        'unlinked': unlinked,
        'unlinked_count': unlinked_count,
        'page': page,
        'total_pages': total_pages,
        'per_page': PER_PAGE,
    })


# ── Cash Accounts ─────────────────────────────────────────────────────────────

def dds_account_list(request):
    """List all cash accounts grouped by ЖК with per-ЖК totals and block breakdown."""
    from collections import defaultdict

    date_from    = request.GET.get('date_from', '').strip()
    date_to      = request.GET.get('date_to',   '').strip()
    block_filter = request.GET.get('block', '').strip()

    selected_block = None
    if block_filter and block_filter.isdigit():
        selected_block = Block.objects.filter(pk=int(block_filter)).first()

    all_blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))

    # Q for annotated Sum() filters (traverse through records reverse FK)
    rec_q = Q()
    if date_from:
        rec_q &= Q(records__operation_date__gte=date_from)
    if date_to:
        rec_q &= Q(records__operation_date__lte=date_to)
    if selected_block:
        rec_q &= Q(records__block=selected_block)

    # Accounts with annotated totals
    accounts = list(
        CashAccount.objects
        .select_related('residential_complex', 'block')
        .annotate(
            record_count=Count('records'),
            ann_income=Coalesce(
                Sum('records__amount', filter=Q(records__direction='in') & rec_q),
                Value(Decimal('0'))
            ),
            ann_expense=Coalesce(
                Sum('records__amount', filter=Q(records__direction='out') & rec_q),
                Value(Decimal('0'))
            ),
        )
        .order_by('residential_complex__name', 'name')
    )
    for acc in accounts:
        acc.disp_income  = acc.ann_income
        acc.disp_expense = acc.ann_expense
        acc.disp_balance = acc.ann_income - acc.ann_expense

    # Block breakdown
    block_qs = CashFlowRecord.objects.filter(direction__in=['in', 'out'])
    if date_from:
        block_qs = block_qs.filter(operation_date__gte=date_from)
    if date_to:
        block_qs = block_qs.filter(operation_date__lte=date_to)
    if selected_block:
        block_qs = block_qs.filter(block=selected_block)

    block_rows = list(
        block_qs
        .values('account__residential_complex_id', 'block_id', 'block__name', 'direction')
        .annotate(total=Sum('amount'))
        .order_by('account__residential_complex_id', 'block__name')
    )
    rc_block_map = defaultdict(lambda: defaultdict(lambda: {'name': '', 'income': Decimal('0'), 'expense': Decimal('0')}))
    for row in block_rows:
        rc_id = row['account__residential_complex_id']
        bid = row['block_id'] if row['block_id'] is not None else '__none__'
        rc_block_map[rc_id][bid]['name'] = row['block__name'] or 'Без блока'
        if row['direction'] == 'in':
            rc_block_map[rc_id][bid]['income'] += row['total']
        else:
            rc_block_map[rc_id][bid]['expense'] += row['total']

    # Build ordered RC summary list
    all_rc = list(ResidentialComplex.objects.order_by('name'))
    rc_summary = []
    seen_acc_ids = set()

    for rc in all_rc:
        rc_accounts = [a for a in accounts if a.residential_complex_id == rc.pk]
        # When filtering by block, skip accounts with zero activity for that block
        if selected_block:
            rc_accounts = [a for a in rc_accounts if a.disp_income or a.disp_expense]
        if not rc_accounts:
            continue
        seen_acc_ids.update(a.pk for a in rc_accounts)

        rc_income  = sum(a.disp_income  for a in rc_accounts)
        rc_expense = sum(a.disp_expense for a in rc_accounts)

        blocks_raw = rc_block_map.get(rc.pk, {})
        block_list = sorted(
            [{'id': bid, 'name': d['name'],
              'income': d['income'], 'expense': d['expense'],
              'balance': d['income'] - d['expense']}
             for bid, d in blocks_raw.items()],
            key=lambda x: (x['name'] == 'Без блока', x['name'] or '')
        )

        rc_summary.append({
            'rc': rc,
            'accounts': rc_accounts,
            'income':  rc_income,
            'expense': rc_expense,
            'balance': rc_income - rc_expense,
            'blocks':  block_list,
        })

    # Accounts not linked to any RC
    no_rc = [a for a in accounts if a.pk not in seen_acc_ids
             and (not selected_block or a.disp_income or a.disp_expense)]
    if no_rc:
        rc_income  = sum(a.disp_income  for a in no_rc)
        rc_expense = sum(a.disp_expense for a in no_rc)
        rc_summary.append({
            'rc': None,
            'accounts': no_rc,
            'income':  rc_income,
            'expense': rc_expense,
            'balance': rc_income - rc_expense,
            'blocks':  [],
        })

    unlinked_qs = CashFlowRecord.objects
    if date_from:
        unlinked_qs = unlinked_qs.filter(operation_date__gte=date_from)
    if date_to:
        unlinked_qs = unlinked_qs.filter(operation_date__lte=date_to)
    if selected_block:
        unlinked_qs = unlinked_qs.filter(block=selected_block)
    unlinked_no_block = unlinked_qs.filter(block__isnull=True).count() if not selected_block else 0
    unlinked_no_item  = unlinked_qs.filter(
        block__isnull=False, direction='out', estimate_item__isnull=True
    ).count()

    total_income  = sum(s['income']  for s in rc_summary)
    total_expense = sum(s['expense'] for s in rc_summary)

    # Block chart data — flatten all blocks across all RCs
    block_chart_items = []
    for section in rc_summary:
        rc_name = section['rc'].name if section['rc'] else 'Без ЖК'
        for blk in section['blocks']:
            if blk['id'] == '__none__':
                continue
            label = f"{rc_name} / {blk['name']}" if len(rc_summary) > 1 else blk['name']
            block_chart_items.append({
                'label':   label,
                'income':  float(blk['income']),
                'expense': float(blk['expense']),
                'balance': float(blk['balance']),
            })
    block_chart_items.sort(key=lambda x: x['expense'], reverse=True)

    block_chart_labels  = json.dumps([b['label']   for b in block_chart_items])
    block_chart_income  = json.dumps([b['income']  for b in block_chart_items])
    block_chart_expense = json.dumps([b['expense'] for b in block_chart_items])
    block_chart_balance = json.dumps([b['balance'] for b in block_chart_items])

    # Daily chart data (respects all active filters)
    daily_qs = CashFlowRecord.objects.filter(direction__in=['in', 'out'])
    if date_from:
        daily_qs = daily_qs.filter(operation_date__gte=date_from)
    if date_to:
        daily_qs = daily_qs.filter(operation_date__lte=date_to)
    if selected_block:
        daily_qs = daily_qs.filter(block=selected_block)
    daily_rows = list(
        daily_qs
        .values('operation_date', 'direction')
        .annotate(total=Sum('amount'))
        .order_by('operation_date')
    )
    daily_map = {}
    for row in daily_rows:
        d = str(row['operation_date'])
        if d not in daily_map:
            daily_map[d] = {'in': 0.0, 'out': 0.0}
        daily_map[d][row['direction']] += float(row['total'])
    sorted_dates = sorted(daily_map)
    running = 0.0
    daily_balance = []
    for d in sorted_dates:
        running += daily_map[d]['in'] - daily_map[d]['out']
        daily_balance.append(round(running, 2))

    chart_labels  = json.dumps(sorted_dates)
    chart_income  = json.dumps([round(daily_map[d]['in'],  2) for d in sorted_dates])
    chart_expense = json.dumps([round(daily_map[d]['out'], 2) for d in sorted_dates])
    chart_balance = json.dumps(daily_balance)

    return render(request, 'dds/account_list.html', {
        'rc_summary':        rc_summary,
        'accounts':          accounts,
        'unlinked_no_block': unlinked_no_block,
        'unlinked_no_item':  unlinked_no_item,
        'total_income':      total_income,
        'total_expense':     total_expense,
        'total_balance':     total_income - total_expense,
        'date_from':         date_from,
        'date_to':           date_to,
        'block_filter':      block_filter,
        'selected_block':    selected_block,
        'all_blocks':        all_blocks,
        'is_filtered':       bool(date_from or date_to or selected_block),
        'chart_labels':       chart_labels,
        'chart_income':       chart_income,
        'chart_expense':      chart_expense,
        'chart_balance':      chart_balance,
        'has_chart_data':     bool(sorted_dates),
        'block_chart_labels': block_chart_labels,
        'block_chart_income': block_chart_income,
        'block_chart_expense':block_chart_expense,
        'block_chart_balance':block_chart_balance,
        'has_block_chart':    bool(block_chart_items),
    })


def dds_account_detail(request, pk):
    """Cash account detail: all operations with filters and running balance."""
    account = get_object_or_404(
        CashAccount.objects.select_related('residential_complex'), pk=pk
    )

    qs = CashFlowRecord.objects.filter(account=account).select_related('block', 'estimate_item')

    # Filters
    direction = request.GET.get('direction', '')
    block_filter = request.GET.get('block', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search = request.GET.get('q', '')

    if direction in ('in', 'out', 'transfer'):
        qs = qs.filter(direction=direction)
    if block_filter and block_filter.isdigit():
        qs = qs.filter(block_id=int(block_filter))
    if date_from:
        try:
            from datetime import datetime
            qs = qs.filter(operation_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime
            qs = qs.filter(operation_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
    if search:
        qs = qs.filter(
            Q(counterparty__icontains=search) |
            Q(object_ref__icontains=search) |
            Q(description__icontains=search) |
            Q(operation_type__icontains=search)
        )

    records = list(qs.order_by('-operation_date', '-created_at'))

    # Totals for filtered set
    filtered_income = sum(r.amount for r in records if r.direction == 'in')
    filtered_expense = sum(r.amount for r in records if r.direction == 'out')

    # Overall account totals (unfiltered)
    all_records = CashFlowRecord.objects.filter(account=account)
    total_income = all_records.filter(direction='in').aggregate(
        s=Coalesce(Sum('amount'), Value(Decimal('0')))
    )['s']
    total_expense = all_records.filter(direction='out').aggregate(
        s=Coalesce(Sum('amount'), Value(Decimal('0')))
    )['s']
    balance = total_income - total_expense

    # Blocks for filter dropdown
    all_blocks = list(Block.objects.filter(
        residential_complex=account.residential_complex
    ).order_by('name'))

    # Other accounts for this ЖК (sidebar navigation)
    other_accounts = list(
        CashAccount.objects.filter(residential_complex=account.residential_complex)
        .exclude(pk=pk)
        .order_by('name')
    )

    # For edit modals: all RCs, all blocks, item choices as JSON
    from apps.projects.models import ResidentialComplex
    import json as _json
    from collections import defaultdict
    all_rc = list(ResidentialComplex.objects.order_by('name'))
    all_blocks_edit = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))
    # Item choices per block (for record-edit modal)
    from apps.estimates.models import EstimateItem
    _items_qs = list(
        EstimateItem.objects
        .filter(section__estimate__block__in=all_blocks_edit)
        .select_related('section__estimate')
        .order_by('section__code', 'order')
    )
    _items_by_block = defaultdict(list)
    for _it in _items_qs:
        _items_by_block[_it.section.estimate.block_id].append(_it)
    _item_choices_json = {}
    for _bid, _its in _items_by_block.items():
        _choices, _cur_sec = [], None
        for _it in _its:
            _sl = f'{_it.section.code} {_it.section.name}'.strip()
            if _sl != _cur_sec:
                _choices.append({'t': 'g', 'l': _sl})
                _cur_sec = _sl
            _lbl = f'{_it.code} {_it.name}'.strip() if _it.code else _it.name
            _choices.append({'t': 'o', 'id': _it.pk, 'l': _lbl})
        _item_choices_json[_bid] = _choices
    item_choices_json = _json.dumps(_item_choices_json, ensure_ascii=False)

    # Daily chart — same queryset as records table (respects all filters)
    chart_qs = CashFlowRecord.objects.filter(account=account, direction__in=['in', 'out'])
    if date_from:
        try:
            from datetime import datetime as _dt
            chart_qs = chart_qs.filter(operation_date__gte=_dt.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime as _dt
            chart_qs = chart_qs.filter(operation_date__lte=_dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
    if block_filter and block_filter.isdigit():
        chart_qs = chart_qs.filter(block_id=int(block_filter))

    daily_rows = list(
        chart_qs
        .values('operation_date', 'direction')
        .annotate(total=Sum('amount'))
        .order_by('operation_date')
    )
    daily_map = {}
    for row in daily_rows:
        d = str(row['operation_date'])
        if d not in daily_map:
            daily_map[d] = {'in': 0.0, 'out': 0.0}
        daily_map[d][row['direction']] += float(row['total'])
    sorted_dates = sorted(daily_map)
    running, daily_balance = 0.0, []
    for d in sorted_dates:
        running += daily_map[d]['in'] - daily_map[d]['out']
        daily_balance.append(round(running, 2))

    import json as _json2
    chart_labels  = _json2.dumps(sorted_dates)
    chart_income  = _json2.dumps([round(daily_map[d]['in'],  2) for d in sorted_dates])
    chart_expense = _json2.dumps([round(daily_map[d]['out'], 2) for d in sorted_dates])
    chart_balance = _json2.dumps(daily_balance)

    return render(request, 'dds/account_detail.html', {
        'account': account,
        'records': records,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'filtered_income': filtered_income,
        'filtered_expense': filtered_expense,
        'all_blocks': all_blocks,
        'other_accounts': other_accounts,
        'all_rc': all_rc,
        'all_blocks_edit': all_blocks_edit,
        'item_choices_json': item_choices_json,
        'f_direction': direction,
        'f_block': block_filter,
        'f_date_from': date_from,
        'f_date_to': date_to,
        'f_q': search,
        'chart_labels':  chart_labels,
        'chart_income':  chart_income,
        'chart_expense': chart_expense,
        'chart_balance': chart_balance,
        'has_chart_data': bool(sorted_dates),
    })


# ── Account edit ─────────────────────────────────────────────────────────────

def dds_account_edit(request, pk):
    """Edit CashAccount: name, type, RC, block, notes."""
    account = get_object_or_404(CashAccount, pk=pk)

    if request.method != 'POST':
        return redirect('dds_account_detail', pk=pk)

    name = request.POST.get('name', '').strip()
    account_type = request.POST.get('account_type', '').strip()
    rc_val = request.POST.get('residential_complex', '').strip()
    block_val = request.POST.get('block', '').strip()
    notes = request.POST.get('notes', '').strip()

    errors = []
    if not name:
        errors.append('Название не может быть пустым.')
    if account_type not in ('cash', 'bank'):
        errors.append('Неверный тип счёта.')

    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect('dds_account_detail', pk=pk)

    account.name = name
    account.account_type = account_type
    account.notes = notes

    if rc_val and rc_val.isdigit():
        from apps.projects.models import ResidentialComplex
        account.residential_complex = ResidentialComplex.objects.filter(pk=int(rc_val)).first()
    else:
        account.residential_complex = None

    if block_val and block_val.isdigit():
        account.block = Block.objects.filter(pk=int(block_val)).first()
    else:
        account.block = None

    account.save()
    messages.success(request, f'Касса «{account.name}» обновлена.')
    return redirect('dds_account_detail', pk=pk)


# ── Manual record creation ────────────────────────────────────────────────────

def dds_record_create(request, pk):
    """Create a single CashFlowRecord manually for a given account."""
    account = get_object_or_404(CashAccount.objects.select_related('residential_complex'), pk=pk)

    if request.method != 'POST':
        return redirect('dds_account_detail', pk=pk)

    from datetime import date as _date
    errors = []

    raw_date = request.POST.get('operation_date', '').strip()
    raw_amount = request.POST.get('amount', '').strip().replace(',', '.')
    direction = request.POST.get('direction', '').strip()
    operation_type = request.POST.get('operation_type', '').strip()
    counterparty = request.POST.get('counterparty', '').strip()
    object_ref = request.POST.get('object_ref', '').strip()
    description = request.POST.get('description', '').strip()
    block_val = request.POST.get('block', '').strip()

    try:
        op_date = _date.fromisoformat(raw_date)
    except (ValueError, TypeError):
        errors.append('Неверная дата.')
        op_date = None

    try:
        amount = Decimal(raw_amount)
        if amount <= 0:
            errors.append('Сумма должна быть больше нуля.')
    except Exception:
        errors.append('Неверная сумма.')
        amount = None

    if direction not in ('in', 'out', 'transfer'):
        errors.append('Укажите направление.')

    if not operation_type:
        errors.append('Укажите тип операции.')

    block = None
    if block_val and block_val.isdigit():
        block = Block.objects.filter(pk=int(block_val)).first()

    if not errors:
        CashFlowRecord.objects.create(
            account=account,
            operation_date=op_date,
            direction=direction,
            amount=amount,
            operation_type=operation_type,
            counterparty=counterparty,
            object_ref=object_ref,
            description=description,
            block=block,
            account_name=account.name,
            bank_or_cash='Касса' if account.account_type == 'cash' else 'Банк',
        )
        messages.success(request, 'Операция добавлена.')
    else:
        for e in errors:
            messages.error(request, e)

    return redirect('dds_account_detail', pk=pk)


def dds_record_edit(request, pk):
    """Edit a single CashFlowRecord."""
    rec = get_object_or_404(CashFlowRecord.objects.select_related('account'), pk=pk)
    account_pk = rec.account_id

    if request.method != 'POST':
        return redirect('dds_account_detail', pk=account_pk)

    from datetime import date as _date
    errors = []

    raw_date     = request.POST.get('operation_date', '').strip()
    raw_amount   = request.POST.get('amount', '').strip().replace(',', '.')
    direction    = request.POST.get('direction', '').strip()
    operation_type = request.POST.get('operation_type', '').strip()
    counterparty = request.POST.get('counterparty', '').strip()
    object_ref   = request.POST.get('object_ref', '').strip()
    description  = request.POST.get('description', '').strip()
    block_val    = request.POST.get('block', '').strip()
    item_val     = request.POST.get('estimate_item', '').strip()

    try:
        op_date = _date.fromisoformat(raw_date)
    except (ValueError, TypeError):
        errors.append('Неверная дата.')
        op_date = None

    try:
        amount = Decimal(raw_amount)
        if amount <= 0:
            errors.append('Сумма должна быть больше нуля.')
    except Exception:
        errors.append('Неверная сумма.')
        amount = None

    if direction not in ('in', 'out', 'transfer'):
        errors.append('Укажите направление.')
    if not operation_type:
        errors.append('Укажите тип операции.')

    block = None
    if block_val and block_val.isdigit():
        block = Block.objects.filter(pk=int(block_val)).first()

    from apps.estimates.models import EstimateItem
    estimate_item = None
    if item_val and item_val.isdigit():
        estimate_item = EstimateItem.objects.filter(pk=int(item_val)).first()

    if not errors:
        rec.operation_date  = op_date
        rec.direction       = direction
        rec.amount          = amount
        rec.operation_type  = operation_type
        rec.counterparty    = counterparty
        rec.object_ref      = object_ref
        rec.description     = description
        rec.block           = block
        rec.estimate_item   = estimate_item
        rec.save()
        messages.success(request, 'Запись обновлена.')
    else:
        for e in errors:
            messages.error(request, e)

    return redirect('dds_account_detail', pk=account_pk)


def dds_record_delete(request, pk):
    """Delete a single CashFlowRecord."""
    rec = get_object_or_404(CashFlowRecord.objects.select_related('account'), pk=pk)
    account_pk = rec.account_id

    if request.method == 'POST':
        rec.delete()
        messages.success(request, 'Запись удалена.')

    return redirect('dds_account_detail', pk=account_pk)


# ── Plan-fact upload → unlinked DDS records ──────────────────────────────────

def dds_planfact_upload(request):
    """
    Upload a plan-fact Excel (floor-expense format) and create unlinked
    CashFlowRecord entries (direction='out', block=selected, estimate_item=None).
    They appear immediately in DDS unlinked → Tab 2 for item linking.
    """
    import tempfile, os
    from datetime import date as _date

    all_blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))

    if request.method != 'POST':
        return render(request, 'dds/import_planfact.html', {'all_blocks': all_blocks})

    block_val = request.POST.get('block', '').strip()
    uploaded  = request.FILES.get('file')

    errors = []
    if not block_val or not block_val.isdigit():
        errors.append('Выберите блок.')
    if not uploaded:
        errors.append('Выберите файл.')

    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, 'dds/import_planfact.html', {'all_blocks': all_blocks})

    block = Block.objects.filter(pk=int(block_val)).select_related('residential_complex').first()
    if not block:
        messages.error(request, 'Блок не найден.')
        return render(request, 'dds/import_planfact.html', {'all_blocks': all_blocks})

    ext = uploaded.name.rsplit('.', 1)[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
        for chunk in uploaded.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        from apps.imports.floor_parser import parse_floor_excel
        parsed = parse_floor_excel(tmp_path)
        items  = parsed.get('items', [])
        today  = _date.today()

        to_create = []
        skipped   = 0
        for item in items:
            amount = item.get('total_amount', Decimal('0'))
            if amount <= 0:
                skipped += 1
                continue
            op_date = item.get('expense_date') or today
            name    = item.get('name', '') or ''
            code    = item.get('item_code', '') or ''
            desc    = f'{code} {name}'.strip() if code else name

            to_create.append(CashFlowRecord(
                operation_date  = op_date,
                bank_or_cash    = 'Расход',
                operation_type  = 'Расход (план-факт)',
                direction       = 'out',
                amount          = amount,
                transfer_amount = Decimal('0'),
                counterparty    = '',
                account_name    = 'Расход план-факт',
                object_ref      = f'Блок {block.name}',
                description     = desc,
                block           = block,
            ))

        CashFlowRecord.objects.bulk_create(to_create)
        msg = f'Импортировано {len(to_create)} расходов в блок «{block.name}» — ожидают привязки к смете.'
        if skipped:
            msg += f' Пропущено {skipped} строк с нулевой суммой.'
        messages.success(request, msg)

    except Exception as e:
        messages.error(request, f'Ошибка импорта: {e}')
        return render(request, 'dds/import_planfact.html', {'all_blocks': all_blocks})
    finally:
        os.unlink(tmp_path)

    return redirect('dds_unlinked')


# ── Unlinked DDS records ──────────────────────────────────────────────────────

def dds_unlinked(request):
    """
    Two-tab page for unlinked DDS records:
      Tab 1 — records without a block (need block assignment)
      Tab 2 — expense records with block but no estimate_item (need item linking)
    """
    rc_filter = request.GET.get('rc', '')
    tab = request.GET.get('tab', 'no_block')
    search = request.GET.get('q', '')

    all_complexes = list(ResidentialComplex.objects.order_by('name'))
    rc_obj = None
    if rc_filter and rc_filter.isdigit():
        rc_obj = next((r for r in all_complexes if r.pk == int(rc_filter)), None)

    # ── Tab 1: no block ──────────────────────────────────────────────────────
    no_block_qs = CashFlowRecord.objects.filter(block__isnull=True).select_related('account', 'source_import')
    if rc_obj:
        no_block_qs = no_block_qs.filter(account__residential_complex=rc_obj)
    if search:
        no_block_qs = no_block_qs.filter(
            Q(counterparty__icontains=search) | Q(object_ref__icontains=search) |
            Q(description__icontains=search) | Q(operation_type__icontains=search)
        )
    no_block_records = list(no_block_qs.order_by('-operation_date')[:200])

    # ── Tab 2: has block, no estimate_item (expenses only) ───────────────────
    no_item_qs = CashFlowRecord.objects.filter(
        block__isnull=False,
        direction='out',
        estimate_item__isnull=True,
    ).select_related('block', 'account')
    if rc_obj:
        no_item_qs = no_item_qs.filter(block__residential_complex=rc_obj)
    if search:
        no_item_qs = no_item_qs.filter(
            Q(counterparty__icontains=search) | Q(object_ref__icontains=search) |
            Q(description__icontains=search) | Q(operation_type__icontains=search)
        )
    no_item_records = list(no_item_qs.order_by('block__name', '-operation_date')[:300])

    # Blocks for assignment dropdown (filter by ЖК if selected)
    blocks_qs = Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    )
    if rc_obj:
        blocks_qs = blocks_qs.filter(residential_complex=rc_obj)
    all_blocks = list(blocks_qs)

    # Build block choices grouped by ЖК
    block_choices = []
    cur_rc = None
    for b in all_blocks:
        rc_label = b.residential_complex.name
        if rc_label != cur_rc:
            block_choices.append({'type': 'optgroup', 'label': rc_label})
            cur_rc = rc_label
        block_choices.append({'type': 'option', 'id': b.pk, 'label': b.name})

    # Estimate item choices per block (for tab 2) — avoid giant shared list
    from apps.estimates.models import EstimateItem
    from collections import defaultdict
    _all_items = list(
        EstimateItem.objects.filter(section__estimate__block__in=all_blocks)
        .select_related('section__estimate')
        .order_by('section__code', 'order')
    )
    _items_by_block = defaultdict(list)
    for _it in _all_items:
        _items_by_block[_it.section.estimate.block_id].append(_it)

    import json as _json
    item_choices_json = {}
    for _blk_id, _items in _items_by_block.items():
        _choices = []
        _cur_sec = None
        for _it in _items:
            _sec_label = f'{_it.section.code} {_it.section.name}'.strip()
            if _sec_label != _cur_sec:
                _choices.append({'t': 'g', 'l': _sec_label})
                _cur_sec = _sec_label
            _lbl = f'{_it.code} {_it.name}'.strip() if _it.code else _it.name
            _choices.append({'t': 'o', 'id': _it.pk, 'l': _lbl})
        item_choices_json[_blk_id] = _choices
    item_choices_json_str = _json.dumps(item_choices_json, ensure_ascii=False)

    # Counts (unfiltered for badges)
    total_no_block = CashFlowRecord.objects.filter(block__isnull=True).count()
    total_no_item = CashFlowRecord.objects.filter(
        block__isnull=False, direction='out', estimate_item__isnull=True
    ).count()

    if request.method == 'POST':
        saved_block = 0
        saved_item = 0
        post_tab = request.POST.get('tab', 'no_block')

        if post_tab == 'no_block':
            for rec in no_block_records:
                val = request.POST.get(f'block_{rec.pk}', '').strip()
                if val and val.isdigit():
                    new_block = next((b for b in all_blocks if b.pk == int(val)), None)
                    if new_block and rec.block_id != new_block.pk:
                        rec.block = new_block
                        rec.save(update_fields=['block'])
                        saved_block += 1
            messages.success(request, f'Привязано к блоку: {saved_block} записей.')
        else:
            from apps.estimates.models import EstimateItem
            item_map = {
                i.pk: i for i in EstimateItem.objects.filter(
                    section__estimate__block__in=all_blocks
                )
            }
            for rec in no_item_records:
                val = request.POST.get(f'item_{rec.pk}', '').strip()
                if val and val.isdigit():
                    item = item_map.get(int(val))
                    if item and rec.estimate_item_id != item.pk:
                        rec.estimate_item = item
                        rec.save(update_fields=['estimate_item'])
                        saved_item += 1
            messages.success(request, f'Привязано к позиции сметы: {saved_item} записей.')

        return redirect(f"{request.path}?tab={post_tab}&rc={rc_filter}&q={search}")

    return render(request, 'dds/unlinked.html', {
        'no_block_records': no_block_records,
        'no_item_records': no_item_records,
        'block_choices': block_choices,
        'item_choices_json': item_choices_json_str,
        'all_complexes': all_complexes,
        'all_blocks': all_blocks,
        'total_no_block': total_no_block,
        'total_no_item': total_no_item,
        'tab': tab,
        'f_rc': rc_filter,
        'f_q': search,
    })
