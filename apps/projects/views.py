import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count
from django.db.models.functions import Coalesce
from django.db.models import Value
from django.contrib.auth.decorators import login_required

from apps.core.decorators import editor_required
from .models import Organization, ResidentialComplex, Block, Stage, Floor, FloorExpense
from .forms import (OrganizationForm, ResidentialComplexForm, BlockForm,
                    StageForm, FloorForm, FloorExpenseForm)


# ── Organization ──────────────────────────────────────────────────────────────

def org_list(request):
    orgs = Organization.objects.prefetch_related('complexes').all()
    return render(request, 'projects/org_list.html', {'orgs': orgs})


def org_detail(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    complexes = org.complexes.prefetch_related('blocks__stages__floors__expenses').all()

    stats = []
    for c in complexes:
        planned = c.total_planned_expenses
        actual = c.total_actual_expenses
        stats.append({'complex': c, 'planned': planned, 'actual': actual,
                       'deviation': actual - planned})

    total_planned = sum(s['planned'] for s in stats)
    total_actual = sum(s['actual'] for s in stats)

    context = {
        'org': org,
        'stats': stats,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_deviation': total_actual - total_planned,
        'chart_labels': json.dumps([s['complex'].name for s in stats]),
        'chart_planned': json.dumps([float(s['planned']) for s in stats]),
        'chart_actual': json.dumps([float(s['actual']) for s in stats]),
    }
    return render(request, 'projects/org_detail.html', context)


@editor_required
def org_create(request):
    if request.method == 'POST':
        form = OrganizationForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Организация «{obj.name}» создана.')
            return redirect('org_detail', pk=obj.pk)
    else:
        form = OrganizationForm()
    return render(request, 'projects/org_form.html', {'form': form, 'title': 'Добавить организацию'})


@editor_required
def org_update(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    if request.method == 'POST':
        form = OrganizationForm(request.POST, instance=org)
        if form.is_valid():
            form.save()
            messages.success(request, f'Организация «{org.name}» обновлена.')
            return redirect('org_detail', pk=pk)
    else:
        form = OrganizationForm(instance=org)
    return render(request, 'projects/org_form.html',
                  {'form': form, 'title': 'Редактировать организацию', 'object': org})


@editor_required
def org_delete(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    if request.method == 'POST':
        name = org.name
        org.delete()
        messages.success(request, f'Организация «{name}» удалена.')
        return redirect('org_list')
    return render(request, 'projects/org_confirm_delete.html', {'org': org})


# ── ResidentialComplex ────────────────────────────────────────────────────────

def complex_list(request):
    complexes = ResidentialComplex.objects.select_related('organization').prefetch_related('blocks__stages').all()
    stats = []
    for c in complexes:
        planned = c.total_planned_expenses
        actual = c.total_actual_expenses
        sqm = c.square_meters
        price_per_sqm = (actual / sqm).quantize(Decimal('0.01')) if sqm else None
        stats.append({'complex': c, 'planned': planned, 'actual': actual,
                       'deviation': actual - planned, 'blocks_count': c.blocks.count(),
                       'price_per_sqm': price_per_sqm})
    return render(request, 'projects/complex_list.html', {'stats': stats})


def complex_detail(request, pk):
    complex_obj = get_object_or_404(ResidentialComplex.objects.select_related('organization'), pk=pk)
    blocks = complex_obj.blocks.prefetch_related('stages__floors__expenses').all()

    block_stats = []
    for b in blocks:
        planned = b.total_planned_expenses
        actual = b.total_actual_expenses
        sqm = b.square_meters
        price_per_sqm = (actual / sqm).quantize(Decimal('0.01')) if sqm else None
        block_stats.append({'block': b, 'planned': planned, 'actual': actual,
                              'deviation': actual - planned, 'stages_count': b.stages.count(),
                              'price_per_sqm': price_per_sqm})

    total_planned = sum(b['planned'] for b in block_stats)
    total_actual = sum(b['actual'] for b in block_stats)

    context = {
        'complex': complex_obj,
        'block_stats': block_stats,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_deviation': total_actual - total_planned,
        'chart_labels': json.dumps([b['block'].name for b in block_stats]),
        'chart_planned': json.dumps([float(b['planned']) for b in block_stats]),
        'chart_actual': json.dumps([float(b['actual']) for b in block_stats]),
    }
    return render(request, 'projects/complex_detail.html', context)


@editor_required
def complex_create(request):
    if request.method == 'POST':
        form = ResidentialComplexForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'ЖК «{obj.name}» создан.')
            return redirect('complex_detail', pk=obj.pk)
    else:
        form = ResidentialComplexForm()
    return render(request, 'projects/complex_form.html', {'form': form, 'title': 'Добавить ЖК'})


@editor_required
def complex_update(request, pk):
    complex_obj = get_object_or_404(ResidentialComplex, pk=pk)
    if request.method == 'POST':
        form = ResidentialComplexForm(request.POST, instance=complex_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'ЖК «{complex_obj.name}» обновлён.')
            return redirect('complex_detail', pk=pk)
    else:
        form = ResidentialComplexForm(instance=complex_obj)
    return render(request, 'projects/complex_form.html',
                  {'form': form, 'title': 'Редактировать ЖК', 'object': complex_obj})


@editor_required
def complex_delete(request, pk):
    complex_obj = get_object_or_404(ResidentialComplex, pk=pk)
    if request.method == 'POST':
        name = complex_obj.name
        complex_obj.delete()
        messages.success(request, f'ЖК «{name}» удалён.')
        return redirect('complex_list')
    return render(request, 'projects/complex_confirm_delete.html', {'complex': complex_obj})


# ── Block ─────────────────────────────────────────────────────────────────────

def block_detail(request, pk):
    block_obj = get_object_or_404(Block.objects.select_related('residential_complex__organization'), pk=pk)
    stages = block_obj.stages.prefetch_related('floors__expenses').all()

    stage_stats = []
    for s in stages:
        planned = s.planned_expenses
        actual = s.computed_actual_expenses
        stage_stats.append({
            'stage': s, 'planned': planned, 'actual': actual,
            'deviation': actual - planned, 'floors_count': s.floors.count(),
            'has_floors': s.has_floors,
        })

    total_planned = sum(x['planned'] for x in stage_stats)
    total_actual = sum(x['actual'] for x in stage_stats)

    # ── Estimate-based plan/fact summary ──────────────────────────────────────
    estimate_summary = None
    estimate_total_plan = None
    estimate_total_fact = Decimal('0')
    try:
        from apps.estimates.models import EstimateItem, ExpenseAllocation
        estimate = block_obj.estimate

        # Section ancestry: sec_id → top_section_id
        sec_parent = dict(estimate.sections.values_list('id', 'parent_id'))

        def _top_id(sec_id):
            seen = set()
            while sec_parent.get(sec_id) is not None:
                if sec_id in seen:
                    break
                seen.add(sec_id)
                sec_id = sec_parent[sec_id]
            return sec_id

        all_items = list(
            EstimateItem.objects.filter(section__estimate=estimate)
            .values('id', 'name', 'section_id')
        )
        item_to_top = {i['id']: _top_id(i['section_id']) for i in all_items}
        item_names = [i['name'] for i in all_items]

        # Auto name-match sums
        pf_by_name = {
            r['name']: r['s']
            for r in FloorExpense.objects.filter(
                floor__stage__block=block_obj, name__in=item_names
            ).values('name').annotate(s=Sum('total_amount'))
        }

        # Manual alloc sums per item
        pf_by_alloc = {
            r['estimate_item_id']: r['s']
            for r in ExpenseAllocation.objects.filter(
                estimate_item__section__estimate=estimate,
                estimate_item__isnull=False,
            ).values('estimate_item_id').annotate(s=Sum('amount'))
        }

        # FE ids already allocated (to exclude from unallocated)
        alloc_fe_ids = set(
            ExpenseAllocation.objects.filter(
                floor_expense__floor__stage__block=block_obj,
                estimate_item__isnull=False,
            ).values_list('floor_expense_id', flat=True)
        )

        # Fact per top section from items (manual overrides auto per item)
        actual_by_top = {}
        for item in all_items:
            fact = pf_by_alloc.get(item['id']) or pf_by_name.get(item['name'], Decimal('0'))
            top = item_to_top[item['id']]
            actual_by_top[top] = actual_by_top.get(top, Decimal('0')) + fact

        # Unallocated FEs per stage (one query)
        unalloc_by_stage = {
            r['floor__stage_id']: r['s']
            for r in FloorExpense.objects.filter(
                floor__stage__block=block_obj
            ).exclude(id__in=alloc_fe_ids)
            .exclude(name__in=item_names)  # exclude auto-matched: already counted per item
            .values('floor__stage_id').annotate(s=Sum('total_amount'))
        }

        stage_by_name = {s.name: s for s in block_obj.stages.all()}
        top_sections = list(estimate.sections.filter(parent__isnull=True).order_by('order', 'code'))

        estimate_summary = []
        for sec in top_sections:
            label = f'{sec.code} {sec.name}'.strip()
            matched_stage = stage_by_name.get(label) or stage_by_name.get(sec.name)
            fact = actual_by_top.get(sec.id, Decimal('0'))
            if matched_stage:
                fact += unalloc_by_stage.get(matched_stage.id, Decimal('0'))
            estimate_summary.append({
                'section': sec,
                'plan': sec.total_amount,
                'fact': fact,
                'deviation': fact - sec.total_amount,
            })

        estimate_total_plan = sum(x['plan'] for x in estimate_summary)
        estimate_total_fact = sum(x['fact'] for x in estimate_summary)

    except Exception:
        pass

    # ── ДДС по блоку ─────────────────────────────────────────────────────────
    dds_income = Decimal('0')
    dds_expense = Decimal('0')
    dds_by_stage = []
    try:
        from apps.dds.models import CashFlowRecord
        from django.db.models import Q
        dds_qs = CashFlowRecord.objects.filter(block=block_obj)
        dds_income = dds_qs.filter(direction='in').aggregate(
            s=Coalesce(Sum('amount'), Value(Decimal('0')))
        )['s']
        dds_expense = dds_qs.filter(direction='out').aggregate(
            s=Coalesce(Sum('amount'), Value(Decimal('0')))
        )['s']

        # Per-stage breakdown (by operation_type grouping for incoming chart)
        stage_income_rows = (
            dds_qs.filter(direction='in')
            .values('operation_type')
            .annotate(s=Sum('amount'))
            .order_by('-s')[:6]
        )
        stage_expense_rows = (
            dds_qs.filter(direction='out')
            .values('operation_type')
            .annotate(s=Sum('amount'))
            .order_by('-s')[:6]
        )
        dds_by_op = {
            'income': list(stage_income_rows),
            'expense': list(stage_expense_rows),
        }
    except Exception:
        dds_by_op = {'income': [], 'expense': []}

    dds_balance = dds_income - dds_expense
    has_dds = dds_income > 0 or dds_expense > 0

    context = {
        'block_obj': block_obj,
        'stage_stats': stage_stats,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_deviation': total_actual - total_planned,
        'estimate_summary': estimate_summary,
        'estimate_total_plan': estimate_total_plan,
        'estimate_total_fact': estimate_total_fact,
        'estimate_total_deviation': estimate_total_fact - (estimate_total_plan or Decimal('0')),
        'dds_income': dds_income,
        'dds_expense': dds_expense,
        'dds_balance': dds_balance,
        'dds_by_op': dds_by_op,
        'has_dds': has_dds,
        'chart_labels': json.dumps([x['stage'].name for x in stage_stats]),
        'chart_planned': json.dumps([float(x['planned']) for x in stage_stats]),
        'chart_actual': json.dumps([float(x['actual']) for x in stage_stats]),
        'est_chart_labels': json.dumps([f'{x["section"].code} {x["section"].name}'.strip() for x in (estimate_summary or [])]),
        'est_chart_plan': json.dumps([float(x['plan']) for x in (estimate_summary or [])]),
        'est_chart_fact': json.dumps([float(x['fact']) for x in (estimate_summary or [])]),
        'dds_income_labels': json.dumps([r['operation_type'] for r in dds_by_op['income']]),
        'dds_income_data': json.dumps([float(r['s']) for r in dds_by_op['income']]),
        'dds_expense_labels': json.dumps([r['operation_type'] for r in dds_by_op['expense']]),
        'dds_expense_data': json.dumps([float(r['s']) for r in dds_by_op['expense']]),
    }
    return render(request, 'projects/block_detail.html', context)


@editor_required
def block_create(request, complex_pk):
    complex_obj = get_object_or_404(ResidentialComplex, pk=complex_pk)
    if request.method == 'POST':
        form = BlockForm(request.POST)
        if form.is_valid():
            new_block = form.save(commit=False)
            new_block.residential_complex = complex_obj
            new_block.save()
            messages.success(request, f'Блок «{new_block.name}» добавлен.')
            return redirect('block_detail', pk=new_block.pk)
    else:
        form = BlockForm()
    return render(request, 'projects/block_form.html',
                  {'form': form, 'complex_obj': complex_obj, 'title': 'Добавить блок'})


@editor_required
def block_update(request, pk):
    block_obj = get_object_or_404(Block.objects.select_related('residential_complex'), pk=pk)
    if request.method == 'POST':
        form = BlockForm(request.POST, instance=block_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Блок «{block_obj.name}» обновлён.')
            return redirect('block_detail', pk=pk)
    else:
        form = BlockForm(instance=block_obj)
    return render(request, 'projects/block_form.html', {
        'form': form, 'complex_obj': block_obj.residential_complex,
        'block_obj': block_obj, 'title': 'Редактировать блок'
    })


@editor_required
def block_delete(request, pk):
    block_obj = get_object_or_404(Block.objects.select_related('residential_complex'), pk=pk)
    if request.method == 'POST':
        complex_pk = block_obj.residential_complex_id
        name = block_obj.name
        block_obj.delete()
        messages.success(request, f'Блок «{name}» удалён.')
        return redirect('complex_detail', pk=complex_pk)
    return render(request, 'projects/block_confirm_delete.html', {'block_obj': block_obj})


# ── Stage ─────────────────────────────────────────────────────────────────────

def stage_detail(request, pk):
    stage = get_object_or_404(
        Stage.objects.select_related('block__residential_complex__organization'), pk=pk
    )
    floors = stage.floors.prefetch_related('expenses').all()

    floor_stats = []
    for f in floors:
        floor_stats.append({'floor': f, 'total': f.total_expenses, 'expenses_count': f.expenses_count})

    # Expenses grouped by name across all floors in this stage
    raw_expenses = FloorExpense.objects.filter(
        floor__stage=stage
    ).select_related('floor').order_by('name', '-created_at')

    stage_grouped = {}
    for exp in raw_expenses:
        key = exp.name
        if key not in stage_grouped:
            stage_grouped[key] = {'name': key, 'unit': exp.unit, 'total_qty': Decimal('0'), 'total_amount': Decimal('0'), 'records': []}
        stage_grouped[key]['total_qty'] += exp.quantity
        stage_grouped[key]['total_amount'] += exp.total_amount
        stage_grouped[key]['records'].append(exp)
    stage_expenses_grouped = sorted(stage_grouped.values(), key=lambda x: -x['total_amount'])

    actual = stage.computed_actual_expenses
    context = {
        'stage': stage,
        'floor_stats': floor_stats,
        'stage_expenses_grouped': stage_expenses_grouped,
        'total_actual': actual,
        'total_planned': stage.planned_expenses,
        'deviation': actual - stage.planned_expenses,
        'chart_labels': json.dumps([x['floor'].display_name for x in floor_stats]),
        'chart_data': json.dumps([float(x['total']) for x in floor_stats]),
    }
    return render(request, 'projects/stage_detail.html', context)


@editor_required
def stage_create(request, block_pk):
    block_obj = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    if request.method == 'POST':
        form = StageForm(request.POST)
        if form.is_valid():
            stage = form.save(commit=False)
            stage.block = block_obj
            stage.save()
            messages.success(request, f'Этап «{stage.name}» добавлен.')
            return redirect('block_detail', pk=block_obj.pk)
    else:
        form = StageForm()
    return render(request, 'projects/stage_form.html',
                  {'form': form, 'block_obj': block_obj, 'title': 'Добавить этап'})


@editor_required
def stage_update(request, pk):
    stage = get_object_or_404(Stage.objects.select_related('block__residential_complex'), pk=pk)
    if request.method == 'POST':
        form = StageForm(request.POST, instance=stage)
        if form.is_valid():
            form.save()
            messages.success(request, f'Этап «{stage.name}» обновлён.')
            return redirect('block_detail', pk=stage.block_id)
    else:
        form = StageForm(instance=stage)
    return render(request, 'projects/stage_form.html', {
        'form': form, 'block_obj': stage.block, 'object': stage, 'title': 'Редактировать этап'
    })


@editor_required
def stage_delete(request, pk):
    stage = get_object_or_404(Stage.objects.select_related('block'), pk=pk)
    if request.method == 'POST':
        block_pk = stage.block_id
        name = stage.name
        stage.delete()
        messages.success(request, f'Этап «{name}» удалён.')
        return redirect('block_detail', pk=block_pk)
    return render(request, 'projects/stage_confirm_delete.html', {'stage': stage})


# ── Floor ─────────────────────────────────────────────────────────────────────

def floor_detail(request, pk):
    floor = get_object_or_404(
        Floor.objects.select_related('stage__block__residential_complex__organization'), pk=pk
    )
    expenses = list(floor.expenses.order_by('name', '-created_at'))
    zero_price_count = sum(1 for e in expenses if e.unit_price == 0)

    # Group by name for summary table
    grouped = {}
    for exp in expenses:
        key = exp.name
        if key not in grouped:
            grouped[key] = {'name': key, 'unit': exp.unit, 'total_qty': Decimal('0'), 'total_amount': Decimal('0'), 'records': []}
        grouped[key]['total_qty'] += exp.quantity
        grouped[key]['total_amount'] += exp.total_amount
        grouped[key]['records'].append(exp)
    expenses_grouped = sorted(grouped.values(), key=lambda x: x['name'])

    context = {
        'floor': floor,
        'expenses': expenses,
        'expenses_grouped': expenses_grouped,
        'total_expenses': floor.total_expenses,
        'zero_price_count': zero_price_count,
    }
    return render(request, 'projects/floor_detail.html', context)


@editor_required
def floor_create(request, stage_pk):
    stage = get_object_or_404(Stage.objects.select_related('block__residential_complex'), pk=stage_pk)
    if request.method == 'POST':
        form = FloorForm(request.POST)
        if form.is_valid():
            fl = form.save(commit=False)
            fl.stage = stage
            fl.save()
            messages.success(request, f'Этаж {fl.number} добавлен.')
            return redirect('floor_detail', pk=fl.pk)
    else:
        form = FloorForm()
    return render(request, 'projects/floor_form.html',
                  {'form': form, 'stage': stage, 'title': 'Добавить этаж'})


@editor_required
def floor_update(request, pk):
    floor = get_object_or_404(Floor.objects.select_related('stage__block__residential_complex'), pk=pk)
    if request.method == 'POST':
        form = FloorForm(request.POST, instance=floor)
        if form.is_valid():
            form.save()
            messages.success(request, f'Этаж {floor.number} обновлён.')
            return redirect('floor_detail', pk=pk)
    else:
        form = FloorForm(instance=floor)
    return render(request, 'projects/floor_form.html', {
        'form': form, 'stage': floor.stage, 'object': floor, 'title': 'Редактировать этаж'
    })


@editor_required
def floor_delete(request, pk):
    floor = get_object_or_404(Floor.objects.select_related('stage'), pk=pk)
    if request.method == 'POST':
        stage_pk = floor.stage_id
        num = floor.number
        floor.delete()
        messages.success(request, f'Этаж {num} удалён.')
        return redirect('stage_detail', pk=stage_pk)
    return render(request, 'projects/floor_confirm_delete.html', {'floor': floor})


# ── FloorExpense ──────────────────────────────────────────────────────────────

@editor_required
def expense_create(request, floor_pk):
    floor = get_object_or_404(Floor.objects.select_related('stage__block__residential_complex'), pk=floor_pk)
    if request.method == 'POST':
        form = FloorExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.floor = floor
            # Auto-compute total if not set
            if not expense.total_amount and expense.unit_price and expense.quantity:
                expense.total_amount = expense.unit_price * expense.quantity
            expense.save()
            messages.success(request, f'Расход «{expense.name}» добавлен.')
            if hasattr(floor.stage.block, 'estimate'):
                return redirect('floor_allocate_review', floor_pk=floor.pk)
            return redirect('floor_detail', pk=floor.pk)
    else:
        form = FloorExpenseForm()
    return render(request, 'projects/expense_form.html',
                  {'form': form, 'floor': floor, 'title': 'Добавить расход'})


@editor_required
def expense_update(request, pk):
    expense = get_object_or_404(FloorExpense.objects.select_related('floor__stage__block__residential_complex'), pk=pk)
    if request.method == 'POST':
        form = FloorExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            exp = form.save(commit=False)
            if not exp.total_amount and exp.unit_price and exp.quantity:
                exp.total_amount = exp.unit_price * exp.quantity
            exp.save()
            messages.success(request, f'Расход «{expense.name}» обновлён.')
            return redirect('floor_detail', pk=expense.floor_id)
    else:
        form = FloorExpenseForm(instance=expense)
    return render(request, 'projects/expense_form.html', {
        'form': form, 'floor': expense.floor, 'object': expense, 'title': 'Редактировать расход'
    })


@editor_required
def expense_delete(request, pk):
    expense = get_object_or_404(FloorExpense.objects.select_related('floor'), pk=pk)
    if request.method == 'POST':
        floor_pk = expense.floor_id
        name = expense.name
        expense.delete()
        messages.success(request, f'Расход «{name}» удалён.')
        return redirect('floor_detail', pk=floor_pk)
    return render(request, 'projects/expense_confirm_delete.html', {'expense': expense})


# ── AJAX helpers for cascading dropdowns ─────────────────────────────────────

from django.http import JsonResponse

def ajax_complexes(request):
    org_id = request.GET.get('org_id')
    data = list(ResidentialComplex.objects.filter(
        organization_id=org_id
    ).values('id', 'name')) if org_id else []
    return JsonResponse(data, safe=False)


def ajax_blocks(request):
    cx_id = request.GET.get('complex_id')
    data = list(Block.objects.filter(
        residential_complex_id=cx_id
    ).values('id', 'name')) if cx_id else []
    return JsonResponse(data, safe=False)


def ajax_stages(request):
    bl_id = request.GET.get('block_id')
    data = list(Stage.objects.filter(
        block_id=bl_id
    ).values('id', 'name')) if bl_id else []
    return JsonResponse(data, safe=False)


def ajax_floors(request):
    st_id = request.GET.get('stage_id')
    floors = []
    if st_id:
        for f in Floor.objects.filter(stage_id=st_id):
            floors.append({'id': f.pk, 'name': f.display_name})
    return JsonResponse(floors, safe=False)


def estimate_for_block(request, block_pk):
    from apps.estimates.models import Estimate
    block = get_object_or_404(Block, pk=block_pk)
    estimate, _ = Estimate.objects.get_or_create(
        block=block,
        defaults={'name': f'Смета блока {block.name}'}
    )
    return redirect('estimate_detail', pk=estimate.pk)
