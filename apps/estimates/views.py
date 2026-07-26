import os
import tempfile
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value

from apps.core.decorators import editor_required
from apps.projects.models import Block, FloorExpense
from .models import (
    Estimate, EstimateSection, EstimateItem,
    Nomenclature, NomenclatureAlias, NomenclatureGroup,
    EstimateVersion, EstimateChangeLog, EstimateItemExpenseLink,
    ExpenseAllocation,
)
from .forms import EstimateImportForm, EstimateItemForm, EstimateSectionForm, NomenclatureForm
from .estimate_parser import parse_estimate_excel, apply_estimate_import


# ── Estimate ──────────────────────────────────────────────────────────────────

def estimate_list(request):
    estimates = Estimate.objects.select_related(
        'block__residential_complex__organization'
    ).order_by('block__residential_complex__name', 'block__name')
    return render(request, 'estimates/estimate_list.html', {'estimates': estimates})


def estimate_detail(request, pk):
    estimate = get_object_or_404(
        Estimate.objects.select_related('block__residential_complex__organization'), pk=pk
    )

    # Fetch all sections and items in 2 queries, then build the tree in Python
    all_sections = list(estimate.sections.order_by('order', 'code'))
    all_items = list(
        EstimateItem.objects.filter(section__estimate=estimate)
        .select_related('nomenclature')
        .prefetch_related('history')
        .order_by('order', 'name')
    )

    # ── Расходы ПФ: два уровня ────────────────────────────────────────────────
    # Уровень 1 (автоматический): FloorExpense.name == EstimateItem.name по блоку
    item_names = {item.name: item.pk for item in all_items}
    fe_name_rows = (
        FloorExpense.objects
        .filter(floor__stage__block=estimate.block, name__in=item_names.keys())
        .values('name')
        .annotate(s=Sum('total_amount'))
    )
    pf_by_name = {r['name']: r['s'] for r in fe_name_rows}

    # Детализация по имени для дропдауна (автоматический уровень)
    fe_detail_rows = (
        FloorExpense.objects
        .filter(floor__stage__block=estimate.block, name__in=item_names.keys())
        .select_related('floor__stage', 'floor')
        .order_by('name', 'floor__stage__name', 'floor__number')
    )
    fe_detail_by_name = {}
    for fe in fe_detail_rows:
        fe_detail_by_name.setdefault(fe.name, []).append(fe)

    # Уровень 2 (ручной): ExpenseAllocation — переопределяет автоматику для тех item,
    # где аллокации выставлены вручную
    alloc_rows = ExpenseAllocation.objects.filter(
        estimate_item__section__estimate=estimate,
        estimate_item__isnull=False,
    ).values('estimate_item_id').annotate(s=Sum('amount'))
    pf_by_alloc = {r['estimate_item_id']: r['s'] for r in alloc_rows}

    alloc_details = (
        ExpenseAllocation.objects
        .filter(estimate_item__section__estimate=estimate, estimate_item__isnull=False)
        .select_related('floor_expense__floor__stage', 'floor_expense__floor')
        .order_by('estimate_item_id', 'floor_expense__floor__stage__name')
    )
    detail_by_alloc = {}
    for alloc in alloc_details:
        detail_by_alloc.setdefault(alloc.estimate_item_id, []).append(alloc)

    # Attach to items: ручная аллокация приоритетнее автоматической
    items_by_section = {}
    for item in all_items:
        if item.pk in pf_by_alloc:
            item.pf_expense = pf_by_alloc[item.pk]
            item.pf_source = 'manual'
            item.pf_details = detail_by_alloc.get(item.pk, [])
            item.pf_floors = _group_pf_by_floor_alloc(item.pf_details)
        else:
            item.pf_expense = pf_by_name.get(item.name, Decimal('0'))
            item.pf_source = 'auto' if item.pf_expense > 0 else 'none'
            item.pf_details = fe_detail_by_name.get(item.name, [])
            item.pf_floors = _group_pf_by_floor_fe(item.pf_details)
        item.actual = item.pf_expense
        items_by_section.setdefault(item.section_id, []).append(item)

    # Build section map and attach items
    section_map = {s.id: s for s in all_sections}
    for s in all_sections:
        s.plan_items = items_by_section.get(s.id, [])
        s.plan_children = []
        s.actual = Decimal('0')
        s.pf_expense = Decimal('0')

    # Link children
    for s in all_sections:
        if s.parent_id and s.parent_id in section_map:
            section_map[s.parent_id].plan_children.append(s)

    # Compute pf_expense bottom-up
    def _compute_actual(section):
        total = sum(i.pf_expense for i in section.plan_items)
        for child in section.plan_children:
            total += _compute_actual(child)
        section.actual = total
        section.pf_expense = total
        return total

    top_sections = [s for s in all_sections if not s.parent_id]
    for sec in top_sections:
        _compute_actual(sec)

    # Build flat list for template rendering; also attach flat_children to each top section
    flat_rows = []

    def _flatten(section, level, top_sec=None):
        row = {'type': 'section', 'obj': section, 'level': level}
        flat_rows.append(row)
        if top_sec is not None:
            top_sec.flat_children.append(row)
        for child in section.plan_children:
            _flatten(child, level + 1, top_sec)
        for item in section.plan_items:
            irow = {'type': 'item', 'obj': item, 'level': level + 1}
            flat_rows.append(irow)
            if top_sec is not None:
                top_sec.flat_children.append(irow)

    for sec in top_sections:
        sec.flat_children = []
        flat_rows.append({'type': 'section', 'obj': sec, 'level': 0})
        for child in sec.plan_children:
            _flatten(child, 1, sec)
        for item in sec.plan_items:
            irow = {'type': 'item', 'obj': item, 'level': 1}
            flat_rows.append(irow)
            sec.flat_children.append(irow)

    total_plan = sum(s.total_amount for s in top_sections)
    total_actual = sum(s.actual for s in top_sections)

    versions = list(
        EstimateVersion.objects.filter(estimate=estimate)
        .order_by('-imported_at')
        .prefetch_related('changes')[:20]
    )

    # Build set of item ids that have expense allocations (for "link" icon in template)
    linked_item_ids = set(pf_by_alloc.keys())

    context = {
        'estimate': estimate,
        'estimate_block': estimate.block,
        'top_sections': top_sections,
        'flat_rows': flat_rows,
        'total_plan': total_plan,
        'total_actual': total_actual,
        'total_deviation': total_actual - total_plan,
        'versions': versions,
        'linked_item_ids': linked_item_ids,
    }
    return render(request, 'estimates/estimate_detail.html', context)


@editor_required
def estimate_for_block(request, block_pk):
    block = get_object_or_404(Block.objects.select_related('residential_complex__organization'), pk=block_pk)
    estimate, created = Estimate.objects.get_or_create(
        block=block,
        defaults={'name': f'Смета блока {block.name}'}
    )
    return redirect('estimate_detail', pk=estimate.pk)


@editor_required
def estimate_import(request, pk):
    estimate = get_object_or_404(Estimate, pk=pk)

    if request.method == 'POST':
        form = EstimateImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = request.FILES['file']
            ext = uploaded.name.rsplit('.', 1)[-1].lower()

            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
                for chunk in uploaded.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            try:
                parsed = parse_estimate_excel(tmp_path)
                stats = apply_estimate_import(estimate, parsed, source_file=uploaded.name)
                if parsed.get('title') and not estimate.name:
                    estimate.name = parsed['title']
                    estimate.save(update_fields=['name'])
                messages.success(
                    request,
                    f'Смета импортирована: {stats["sections"]} разделов, '
                    f'{stats["items"]} позиций, '
                    f'{stats["matched"]} совпадений с номенклатурой.'
                )
            except Exception as e:
                messages.error(request, f'Ошибка импорта: {e}')
            finally:
                os.unlink(tmp_path)

            return redirect('estimate_detail', pk=pk)
    else:
        form = EstimateImportForm()

    return render(request, 'estimates/estimate_import.html', {'form': form, 'estimate': estimate})


def estimate_version_detail(request, pk, version_pk):
    estimate = get_object_or_404(Estimate.objects.select_related('block__residential_complex'), pk=pk)
    version = get_object_or_404(EstimateVersion, pk=version_pk, estimate=estimate)
    changes = version.changes.order_by('action', 'item_code', 'item_name')
    return render(request, 'estimates/version_detail.html', {
        'estimate': estimate,
        'estimate_block': estimate.block,
        'version': version,
        'changes': changes,
        'added': changes.filter(action='added'),
        'updated': changes.filter(action='updated'),
        'removed': changes.filter(action='removed'),
    })


@editor_required
def section_item_add(request, section_pk):
    section = get_object_or_404(EstimateSection.objects.select_related('estimate__block'), pk=section_pk)
    estimate = section.estimate

    if request.method == 'POST':
        form = EstimateItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.section = section
            item.order = section.items.count()
            if item.unit_price and item.quantity and not item.total_amount:
                item.total_amount = item.unit_price * item.quantity
            item.save()
            section.recalculate()
            estimate.recalculate_total()
            messages.success(request, 'Позиция добавлена.')
            return redirect('estimate_detail', pk=estimate.pk)
    else:
        form = EstimateItemForm()

    return render(request, 'estimates/item_form.html', {
        'form': form, 'section': section, 'estimate': estimate, 'action': 'Добавить позицию'
    })


@editor_required
def section_item_edit(request, pk):
    item = get_object_or_404(EstimateItem.objects.select_related('section__estimate__block'), pk=pk)
    section = item.section
    estimate = section.estimate

    if request.method == 'POST':
        # Snapshot old values before saving
        old_vals = {
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_amount': item.total_amount,
            'name': item.name,
            'unit': item.unit,
            'note': item.note,
        }
        form = EstimateItemForm(request.POST, instance=item)
        if form.is_valid():
            from django.utils import timezone
            from .models import EstimateItemHistory
            updated = form.save(commit=False)
            if updated.unit_price and updated.quantity and not updated.total_amount:
                updated.total_amount = updated.unit_price * updated.quantity
            updated.is_modified = True
            updated.modified_at = timezone.now()
            updated.save()

            # Record history for changed fields
            tracked = ['quantity', 'unit_price', 'total_amount', 'name', 'unit', 'note']
            history_entries = []
            for field in tracked:
                old_v = old_vals[field]
                new_v = getattr(updated, field)
                if str(old_v) != str(new_v):
                    history_entries.append(EstimateItemHistory(
                        item=updated,
                        field_name=field,
                        old_value=str(old_v),
                        new_value=str(new_v),
                    ))
            if history_entries:
                EstimateItemHistory.objects.bulk_create(history_entries)

            section.recalculate()
            estimate.recalculate_total()
            messages.success(request, 'Позиция обновлена.')
            return redirect('estimate_detail', pk=estimate.pk)
    else:
        form = EstimateItemForm(instance=item)

    return render(request, 'estimates/item_form.html', {
        'form': form, 'section': section, 'estimate': estimate, 'action': 'Редактировать позицию', 'item': item
    })


@editor_required
def section_item_delete(request, pk):
    item = get_object_or_404(EstimateItem.objects.select_related('section__estimate'), pk=pk)
    estimate = item.section.estimate
    if request.method == 'POST':
        section = item.section
        item.delete()
        section.recalculate()
        estimate.recalculate_total()
        messages.success(request, 'Позиция удалена.')
    return redirect('estimate_detail', pk=estimate.pk)


# ── Misc Sections ─────────────────────────────────────────────────────────────

@editor_required
def estimate_add_misc_sections(request, pk):
    if request.method == 'POST':
        estimate = get_object_or_404(Estimate, pk=pk)
        from .estimate_parser import _add_misc_expense_sections
        _add_misc_expense_sections(estimate)
        messages.success(request, 'Разделы «Прочие расходы» добавлены к каждому этапу.')
    return redirect('estimate_detail', pk=pk)


# ── Expense Links ─────────────────────────────────────────────────────────────

@editor_required
def estimate_expense_links(request, pk):
    estimate = get_object_or_404(
        Estimate.objects.select_related('block__residential_complex'), pk=pk
    )
    block = estimate.block

    # All unique expense names with totals
    expense_names = list(
        FloorExpense.objects.filter(floor__stage__block=block)
        .values('name')
        .annotate(total=Sum('total_amount'))
        .order_by('name')
    )

    # All FloorExpense records grouped by name (for POST processing)
    fe_by_name = {}
    for fe in FloorExpense.objects.filter(floor__stage__block=block).select_related('floor'):
        fe_by_name.setdefault(fe.name, []).append(fe)

    # All estimate items
    all_items = list(
        EstimateItem.objects.filter(section__estimate=estimate)
        .select_related('section')
        .order_by('section__code', 'section__name', 'order', 'name')
    )
    item_map = {i.pk: i for i in all_items}

    # Current state: expense_name → item_id (from ExpenseAllocation, newest wins)
    existing = {}
    for alloc in ExpenseAllocation.objects.filter(
        floor_expense__floor__stage__block=block,
        estimate_item__section__estimate=estimate,
        estimate_item__isnull=False,
    ).select_related('floor_expense', 'estimate_item'):
        existing[alloc.floor_expense.name] = alloc.estimate_item_id

    if request.method == 'POST':
        saved = 0
        for exp in expense_names:
            name = exp['name']
            val = request.POST.get(f'link_{name}', '').strip()
            fes = fe_by_name.get(name, [])
            if not fes:
                continue

            if val:
                try:
                    item_id = int(val)
                    item = item_map.get(item_id)
                    if not item:
                        continue
                except ValueError:
                    continue

                for fe in fes:
                    qty = fe.quantity
                    amt = fe.total_amount
                    # Remove old none-placeholder
                    fe.allocations.filter(estimate_item__isnull=True).delete()
                    ExpenseAllocation.objects.update_or_create(
                        floor_expense=fe,
                        estimate_item=item,
                        defaults={'quantity': qty, 'amount': amt},
                    )
                saved += 1
            else:
                # Unlink: remove allocations for this expense name
                for fe in fes:
                    fe.allocations.filter(
                        estimate_item__section__estimate=estimate
                    ).delete()

        messages.success(request, f'Сохранено {saved} привязок.')
        return redirect('estimate_expense_links', pk=pk)

    # Build choices grouped by section for <select>
    item_choices = []
    current_section = None
    for item in all_items:
        sec_label = f'{item.section.code} {item.section.name}'.strip()
        if sec_label != current_section:
            item_choices.append({'type': 'optgroup', 'label': sec_label})
            current_section = sec_label
        item_choices.append({'type': 'option', 'id': item.pk, 'label': f'{item.code} {item.name}'.strip()})

    return render(request, 'estimates/expense_links.html', {
        'estimate': estimate,
        'estimate_block': block,
        'expense_names': expense_names,
        'item_choices': item_choices,
        'existing': existing,
    })


# ── Unlinked Expenses ─────────────────────────────────────────────────────────

def estimate_unlinked(request, pk):
    estimate = get_object_or_404(Estimate.objects.select_related('block'), pk=pk)
    block = estimate.block

    from apps.projects.models import FloorExpense
    from django.db.models import Q

    all_fe = FloorExpense.objects.filter(
        floor__stage__block=block
    ).select_related('floor__stage', 'floor').prefetch_related('allocations')

    unlinked = []
    for fe in all_fe:
        allocs = list(fe.allocations.all())
        if not allocs or all(a.estimate_item_id is None for a in allocs):
            unlinked.append(fe)

    # Filter by stage if requested
    stage_filter = request.GET.get('stage')
    if stage_filter:
        unlinked = [fe for fe in unlinked if str(fe.floor.stage_id) == stage_filter]

    # All items for this estimate (for dropdown)
    all_items = list(
        EstimateItem.objects.filter(section__estimate=estimate)
        .select_related('section')
        .order_by('section__code', 'order')
    )

    stages = list(block.stages.order_by('order'))

    if request.method == 'POST':
        count = 0
        all_fe_post = FloorExpense.objects.filter(
            floor__stage__block=block
        ).prefetch_related('allocations')
        item_map = {str(i.pk): i for i in all_items}

        for fe in all_fe_post:
            item_val = request.POST.get(f'item_{fe.pk}', '').strip()
            if not item_val:
                continue
            item = item_map.get(item_val)
            if not item:
                continue

            # Optional qty — defaults to full quantity of FloorExpense
            qty_val = request.POST.get(f'qty_{fe.pk}', '').strip()
            try:
                qty = Decimal(qty_val.replace(',', '.')) if qty_val else fe.quantity
            except Exception:
                qty = fe.quantity

            # Amount proportional to qty
            if fe.quantity and fe.quantity > 0:
                amt = (fe.total_amount * qty / fe.quantity).quantize(Decimal('0.01'))
            else:
                amt = fe.total_amount

            # Remove old none-placeholder allocations, create real one
            fe.allocations.filter(estimate_item__isnull=True).delete()
            ExpenseAllocation.objects.update_or_create(
                floor_expense=fe,
                estimate_item=item,
                defaults={'quantity': qty, 'amount': amt},
            )
            count += 1

        messages.success(request, f'Сохранено {count} привязок.')
        return redirect('estimate_unlinked', pk=pk)

    return render(request, 'estimates/unlinked.html', {
        'estimate': estimate,
        'estimate_block': block,
        'unlinked': unlinked,
        'all_items': all_items,
        'stages': stages,
        'stage_filter': stage_filter,
    })


# ── Floor Allocate Review ─────────────────────────────────────────────────────

def floor_allocate_review(request, floor_pk):
    """
    Review page shown after importing expenses to a floor.
    Auto-matches FloorExpense → EstimateItem by name, user confirms/adjusts.
    """
    from apps.projects.models import Floor, Stage

    floor = get_object_or_404(
        Floor.objects.select_related('stage__block__residential_complex'), pk=floor_pk
    )
    block = floor.stage.block

    # Block must have an estimate
    try:
        estimate = block.estimate
    except Estimate.DoesNotExist:
        messages.warning(request, 'У этого блока нет сметы. Сначала загрузите смету.')
        return redirect('floor_detail', pk=floor_pk)

    # All estimate items for this block
    all_items = list(
        EstimateItem.objects.filter(section__estimate=estimate)
        .select_related('section__parent')
        .order_by('section__code', 'order')
    )

    # Build name → [items] lookup (case-insensitive)
    name_to_items = {}
    for item in all_items:
        key = item.name.strip().lower()
        name_to_items.setdefault(key, []).append(item)

    # Find EstimateSection matching this stage (top-level, name = "code name")
    stage = floor.stage
    stage_section = None
    for sec in EstimateSection.objects.filter(estimate=estimate, parent__isnull=True):
        label = f'{sec.code} {sec.name}'.strip()
        if label == stage.name or sec.name == stage.name:
            stage_section = sec
            break

    # Get unallocated FloorExpense for this floor
    allocated_fe_ids = set(
        ExpenseAllocation.objects.filter(
            floor_expense__floor=floor,
            estimate_item__isnull=False,
        ).values_list('floor_expense_id', flat=True)
    )
    unallocated = list(
        floor.expenses.exclude(id__in=allocated_fe_ids).order_by('name', '-created_at')
    )

    # Build memory: expense_name → EstimateItem from ALL past allocations in this block
    # This is how the system "remembers" what was linked before
    item_map_by_pk = {i.pk: i for i in all_items}
    memory = {}  # expense_name.lower() → EstimateItem (most recent allocation wins)
    past_allocs = (
        ExpenseAllocation.objects
        .filter(
            floor_expense__floor__stage__block=block,
            estimate_item__isnull=False,
        )
        .select_related('floor_expense', 'estimate_item')
        .order_by('id')  # ascending so latest overwrites earlier
    )
    for alloc in past_allocs:
        key = alloc.floor_expense.name.strip().lower()
        if alloc.estimate_item_id in item_map_by_pk:
            memory[key] = item_map_by_pk[alloc.estimate_item_id]

    if request.method == 'POST':
        saved = 0
        for fe in unallocated:
            val = request.POST.get(f'item_{fe.pk}', '').strip()
            if not val:
                continue
            item = item_map_by_pk.get(int(val)) if val.isdigit() else None
            if not item:
                continue
            qty_val = request.POST.get(f'qty_{fe.pk}', '').strip()
            try:
                qty = Decimal(qty_val.replace(',', '.')) if qty_val else fe.quantity
            except Exception:
                qty = fe.quantity
            if fe.quantity and fe.quantity > 0:
                amt = (fe.total_amount * qty / fe.quantity).quantize(Decimal('0.01'))
            else:
                amt = fe.total_amount
            fe.allocations.filter(estimate_item__isnull=True).delete()
            ExpenseAllocation.objects.update_or_create(
                floor_expense=fe,
                estimate_item=item,
                defaults={'quantity': qty, 'amount': amt},
            )
            saved += 1
        messages.success(request, f'Распределено {saved} расходов по смете.')
        return redirect('floor_detail', pk=floor_pk)

    # Build suggestions for each unallocated expense
    # Priority: 1) memory (past allocation for this name) 2) name match in estimate
    suggestions = []
    for fe in unallocated:
        key = fe.name.strip().lower()

        # Priority 1: remembered from past allocations
        remembered = memory.get(key)
        if remembered:
            suggestions.append({
                'fe': fe,
                'matches': [remembered],
                'auto_item': remembered,
                'status': 'one',
                'from_memory': True,
            })
            continue

        # Priority 2: match by name in estimate
        matches = name_to_items.get(key, [])

        # Prefer matches in same stage section
        if stage_section and matches:
            same_section = [m for m in matches if _item_in_section(m, stage_section)]
            if same_section:
                matches = same_section

        suggestions.append({
            'fe': fe,
            'matches': matches,
            'auto_item': matches[0] if len(matches) == 1 else None,
            'status': 'one' if len(matches) == 1 else ('many' if len(matches) > 1 else 'none'),
            'from_memory': False,
        })

    # Build choices: stage section first, then all remaining items
    if stage_section:
        stage_items = [i for i in all_items if _item_in_section(i, stage_section)]
        other_items = [i for i in all_items if not _item_in_section(i, stage_section)]
        item_choices = _build_item_choices_with_priority(stage_section, stage_items, other_items)
    else:
        item_choices = _build_item_choices(all_items)

    counts = {
        'one': sum(1 for s in suggestions if s['status'] == 'one'),
        'many': sum(1 for s in suggestions if s['status'] == 'many'),
        'none': sum(1 for s in suggestions if s['status'] == 'none'),
    }

    return render(request, 'estimates/floor_allocate_review.html', {
        'floor': floor,
        'stage': stage,
        'estimate': estimate,
        'estimate_block': block,
        'suggestions': suggestions,
        'item_choices': item_choices,
        'stage_section': stage_section,
        'counts': counts,
    })


def _group_pf_by_floor_alloc(allocs):
    """Group ExpenseAllocation list by floor → [{floor, records, total, dates}]"""
    floors = {}
    for alloc in allocs:
        fl = alloc.floor_expense.floor
        if fl.pk not in floors:
            floors[fl.pk] = {'floor': fl, 'records': [], 'total': Decimal('0')}
        floors[fl.pk]['records'].append(alloc)
        floors[fl.pk]['total'] += alloc.amount
    return sorted(floors.values(), key=lambda x: x['floor'].number or 0)


def _group_pf_by_floor_fe(fes):
    """Group FloorExpense list by floor → [{floor, records, total}]"""
    floors = {}
    for fe in fes:
        fl = fe.floor
        if fl.pk not in floors:
            floors[fl.pk] = {'floor': fl, 'records': [], 'total': Decimal('0')}
        floors[fl.pk]['records'].append(fe)
        floors[fl.pk]['total'] += fe.total_amount
    return sorted(floors.values(), key=lambda x: x['floor'].number or 0)


def _item_in_section(item, section):
    """Check if item belongs to given section or any of its children."""
    sec = item.section
    while sec is not None:
        if sec.pk == section.pk:
            return True
        sec = sec.parent
    return False


def _build_item_choices(all_items):
    """Build [{type, label/id}] list for optgroup selects."""
    choices = []
    current_section = None
    for item in all_items:
        sec_label = f'{item.section.code} {item.section.name}'.strip()
        if sec_label != current_section:
            choices.append({'type': 'optgroup', 'label': sec_label})
            current_section = sec_label
        label = f'{item.code}  {item.name}' if item.code else item.name
        choices.append({'type': 'option', 'id': item.pk, 'label': label})
    return choices


def _build_item_choices_with_priority(stage_section, stage_items, other_items):
    """Stage section items first (marked), then all other items."""
    choices = []
    if stage_items:
        sec_label = f'★ {stage_section.code} {stage_section.name}'
        choices.append({'type': 'optgroup', 'label': sec_label})
        for item in stage_items:
            label = f'{item.code}  {item.name}' if item.code else item.name
            choices.append({'type': 'option', 'id': item.pk, 'label': label})

    if other_items:
        choices.append({'type': 'optgroup', 'label': '─── Остальные разделы ───'})
        current_section = None
        for item in other_items:
            sec_label = f'{item.section.code} {item.section.name}'.strip()
            if sec_label != current_section:
                choices.append({'type': 'optgroup', 'label': sec_label})
                current_section = sec_label
            label = f'{item.code}  {item.name}' if item.code else item.name
            choices.append({'type': 'option', 'id': item.pk, 'label': label})
    return choices


# ── Nomenclature ──────────────────────────────────────────────────────────────

def nomenclature_list(request):
    q = request.GET.get('q', '')
    items = Nomenclature.objects.select_related('group').filter(is_active=True)
    if q:
        items = items.filter(name__icontains=q)
    items = items.order_by('name')
    groups = NomenclatureGroup.objects.all()
    return render(request, 'estimates/nomenclature_list.html', {
        'items': items, 'groups': groups, 'q': q
    })


@editor_required
def nomenclature_create(request):
    if request.method == 'POST':
        form = NomenclatureForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Номенклатура добавлена.')
            return redirect('nomenclature_list')
    else:
        form = NomenclatureForm()
    return render(request, 'estimates/nomenclature_form.html', {'form': form, 'action': 'Добавить'})


@editor_required
def nomenclature_edit(request, pk):
    nom = get_object_or_404(Nomenclature, pk=pk)
    if request.method == 'POST':
        form = NomenclatureForm(request.POST, instance=nom)
        if form.is_valid():
            form.save()
            messages.success(request, 'Номенклатура обновлена.')
            return redirect('nomenclature_list')
    else:
        form = NomenclatureForm(instance=nom)
    return render(request, 'estimates/nomenclature_form.html', {'form': form, 'action': 'Редактировать', 'nom': nom})


@editor_required
def nomenclature_delete(request, pk):
    nom = get_object_or_404(Nomenclature, pk=pk)
    if request.method == 'POST':
        nom.is_active = False
        nom.save(update_fields=['is_active'])
        messages.success(request, 'Номенклатура деактивирована.')
    return redirect('nomenclature_list')
