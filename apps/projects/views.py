import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value

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
        stats.append({'complex': c, 'planned': planned, 'actual': actual,
                       'deviation': actual - planned, 'blocks_count': c.blocks.count()})
    return render(request, 'projects/complex_list.html', {'stats': stats})


def complex_detail(request, pk):
    complex_obj = get_object_or_404(ResidentialComplex.objects.select_related('organization'), pk=pk)
    blocks = complex_obj.blocks.prefetch_related('stages__floors__expenses').all()

    block_stats = []
    for b in blocks:
        planned = b.total_planned_expenses
        actual = b.total_actual_expenses
        block_stats.append({'block': b, 'planned': planned, 'actual': actual,
                              'deviation': actual - planned, 'stages_count': b.stages.count()})

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

    context = {
        'block_obj': block_obj,
        'stage_stats': stage_stats,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_deviation': total_actual - total_planned,
        'chart_labels': json.dumps([x['stage'].name for x in stage_stats]),
        'chart_planned': json.dumps([float(x['planned']) for x in stage_stats]),
        'chart_actual': json.dumps([float(x['actual']) for x in stage_stats]),
    }
    return render(request, 'projects/block_detail.html', context)


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

    actual = stage.computed_actual_expenses
    context = {
        'stage': stage,
        'floor_stats': floor_stats,
        'total_actual': actual,
        'total_planned': stage.planned_expenses,
        'deviation': actual - stage.planned_expenses,
        'chart_labels': json.dumps([x['floor'].display_name for x in floor_stats]),
        'chart_data': json.dumps([float(x['total']) for x in floor_stats]),
    }
    return render(request, 'projects/stage_detail.html', context)


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
    expenses = floor.expenses.all()
    zero_price_count = expenses.filter(unit_price=0).count()

    context = {
        'floor': floor,
        'expenses': expenses,
        'total_expenses': floor.total_expenses,
        'zero_price_count': zero_price_count,
    }
    return render(request, 'projects/floor_detail.html', context)


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
            return redirect('floor_detail', pk=floor.pk)
    else:
        form = FloorExpenseForm()
    return render(request, 'projects/expense_form.html',
                  {'form': form, 'floor': floor, 'title': 'Добавить расход'})


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
