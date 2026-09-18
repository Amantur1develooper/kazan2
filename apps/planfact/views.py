from decimal import Decimal
from datetime import date

from django.db.models import Max, Count, Sum, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from django.contrib.auth.models import User
from apps.projects.models import Block
from .models import (WorkCategory, FloorWork, LandscapingWork, WorkAct, BlockFloorConfig,
                     FloorBudget, AsmDocument, AsmItem, BlockAccess,
                     CalendarPlan, CalendarTask, CalendarMonthPlan,
                     AvrDocument, AvrItem, AvrPhoto, FloorCategoryAssignment,
                     MONTHS_RU, MONTHS_SHORT)


def _is_admin_user(user):
    return user.is_staff or user.groups.filter(name='Производство').exists()


def _can_access_block(user, block_pk):
    if _is_admin_user(user):
        return True
    return BlockAccess.objects.filter(user=user, block_id=block_pk).exists()


def production_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if _is_admin_user(request.user):
            return view_func(request, *args, **kwargs)
        if BlockAccess.objects.filter(user=request.user).exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Нет доступа.')
        return redirect('dashboard')
    return wrapper


def staff_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if _is_admin_user(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Нет доступа. Только для администраторов.')
        return redirect('planfact_index')
    return wrapper


def _build_floor_matrix(block, categories, config, budget_map=None, asm_map=None,
                        avr_pct_map=None, floor_assigned=None):
    underground = config.underground_floors
    above = config.total_floors - underground
    floor_numbers = list(range(-underground, 0)) + list(range(1, above + 1))

    works = list(FloorWork.objects.filter(block=block, category__in=categories).select_related('category'))
    work_map = {(w.floor_number, w.category_id): w for w in works}
    if budget_map is None:
        budget_map = {}
    if asm_map is None:
        asm_map = {}
    if avr_pct_map is None:
        avr_pct_map = {}
    if floor_assigned is None:
        floor_assigned = {}

    D0 = Decimal('0')
    floors = []
    for fn in reversed(floor_numbers):
        # Active categories for this floor: custom list if configured, else all
        if fn in floor_assigned:
            active_ids = floor_assigned[fn]
            active_cats = [cat for cat in categories if cat.id in active_ids]
        else:
            active_cats = categories  # default: all

        cats = []
        has_data = False
        floor_asm_total = D0
        for cat in active_cats:
            fw  = work_map.get((fn, cat.id))
            pct = fw.progress_pct if fw else 0
            if fw and (fw.fact_quantity > 0 or fw.planned_quantity > 0):
                has_data = True
            asm = asm_map.get((fn, cat.id), {'count': 0, 'total': D0})
            floor_asm_total += asm['total']
            avr_pct = avr_pct_map.get((fn, cat.id), 0)
            dp = avr_pct if avr_pct > 0 else pct
            cats.append({'category': cat, 'work': fw, 'pct': pct,
                         'asm_count': asm['count'], 'asm_total': asm['total'],
                         'avr_pct': avr_pct, 'display_pct': dp})
        # Overall: average over ALL active categories (0 for unstarted ones)
        overall = round(sum(c['pct'] for c in cats) / len(cats), 1) if cats else 0
        # AVR overall: sum of all active categories / count (unstarted = 0)
        has_avr = any(c['avr_pct'] > 0 for c in cats)
        avr_overall = round(sum(c['avr_pct'] for c in cats) / len(cats), 1) if (cats and has_avr) else 0
        # display_pct: AVR takes priority; fall back to FloorWork if no AVR data
        display_pct = avr_overall if has_avr else overall
        # all active categories for the modal (including non-active-assigned ones shown as inactive)
        all_cats_modal = []
        for cat in categories:
            in_active = cat in active_cats
            fw  = work_map.get((fn, cat.id))
            pct = fw.progress_pct if fw else 0
            asm = asm_map.get((fn, cat.id), {'count': 0, 'total': D0})
            avr_pct = avr_pct_map.get((fn, cat.id), 0)
            dp = avr_pct if avr_pct > 0 else pct
            all_cats_modal.append({'category': cat, 'work': fw, 'pct': pct,
                                   'asm_count': asm['count'], 'asm_total': asm['total'],
                                   'avr_pct': avr_pct, 'display_pct': dp,
                                   'assigned': in_active})
        budget = budget_map.get(fn)
        planned = budget.planned_amount if budget else None
        floors.append({
            'number': fn,
            'label': f'Подвал {abs(fn)}' if fn < 0 else str(fn),
            'is_underground': fn < 0,
            'has_data': has_data,
            'categories': all_cats_modal,   # modal shows all + assigned flag
            'active_cats': cats,            # progress calculated from active only
            'overall_pct': overall,
            'avr_overall_pct': avr_overall,
            'display_pct': display_pct,
            'planned_amount': planned,
            'budget_notes': budget.notes if budget else '',
            'asm_total': floor_asm_total,
            'asm_vs_plan_pct': (
                min(100, round(float(floor_asm_total / planned * 100), 1))
                if planned and planned > 0 else None
            ),
            'asm_vs_plan_raw': (
                round(float(floor_asm_total / planned * 100), 1)
                if planned and planned > 0 else None
            ),
            'asm_overspend': bool(planned and floor_asm_total > planned),
        })
    return floors


@production_required
def planfact_index(request):
    is_admin = _is_admin_user(request.user)
    qs = Block.objects.select_related('residential_complex').order_by('residential_complex__name', 'name')
    if not is_admin:
        accessible = BlockAccess.objects.filter(user=request.user).values_list('block_id', flat=True)
        qs = qs.filter(pk__in=accessible)
    all_blocks = list(qs)

    # Для админа: АСМ у которых есть строки без цены (unit_price = 0, quantity > 0)
    unprice_docs = []
    if is_admin:
        unprice_docs = list(
            AsmDocument.objects.filter(
                items__unit_price=0,
                items__quantity__gt=0,
            ).distinct()
            .select_related('block__residential_complex', 'category')
            .order_by('-created_at')[:20]
        )

    return render(request, 'planfact/index.html', {
        'all_blocks': all_blocks,
        'is_admin': is_admin,
        'unprice_docs': unprice_docs,
    })


@production_required
def planfact_block(request, block_pk):
    if not _can_access_block(request.user, block_pk):
        messages.error(request, 'Нет доступа к этому блоку.')
        return redirect('planfact_index')
    block = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    config, _ = BlockFloorConfig.objects.get_or_create(
        block=block, defaults={'total_floors': 16, 'underground_floors': 0}
    )

    if request.method == 'POST' and 'save_config' in request.POST:
        if not request.user.is_staff:
            messages.error(request, 'Только администратор может менять конфигурацию.')
        else:
            config.total_floors      = int(request.POST.get('total_floors', 16) or 16)
            config.underground_floors = int(request.POST.get('underground_floors', 0) or 0)
            config.has_landscaping   = 'has_landscaping' in request.POST
            config.save()
            messages.success(request, 'Конфигурация сохранена.')
        return redirect('planfact_block', block_pk=block_pk)

    floor_cats = list(WorkCategory.objects.filter(scope__in=['floor', 'general']))
    land_cats  = list(WorkCategory.objects.filter(scope__in=['landscaping', 'general']))

    budget_map = {fb.floor_number: fb for fb in FloorBudget.objects.filter(block=block)}

    # ASM totals per (floor_number, category_id)
    D0 = Decimal('0')
    _item_expr = ExpressionWrapper(
        F('items__quantity') * F('items__unit_price'),
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )
    asm_rows = (
        AsmDocument.objects.filter(block=block)
        .values('floor_number', 'category_id')
        .annotate(
            doc_count=Count('id', distinct=True),
            asm_total=Coalesce(Sum(_item_expr), D0),
        )
    )
    asm_map = {
        (r['floor_number'], r['category_id']): {'count': r['doc_count'], 'total': r['asm_total']}
        for r in asm_rows
    }
    # Only accepted ASMs count as expenses
    asm_accepted_qs = AsmDocument.objects.filter(block=block, is_accepted=True)
    asm_accepted_manual = asm_accepted_qs.filter(
        accepted_amount__isnull=False).aggregate(s=Coalesce(Sum('accepted_amount'), D0))['s']
    asm_accepted_items  = asm_accepted_qs.filter(
        accepted_amount__isnull=True).aggregate(s=Coalesce(Sum(_item_expr), D0))['s']
    asm_grand_total = asm_accepted_manual + asm_accepted_items

    # AVR completion % per (floor_number, category_id) — sum of all AVR completion_pct
    avr_pct_rows = (
        AvrDocument.objects.filter(block=block)
        .values('floor_number', 'category_id')
        .annotate(total_pct=Coalesce(Max('completion_pct'), D0))
    )
    avr_pct_map = {
        (r['floor_number'], r['category_id']): float(r['total_pct'])
        for r in avr_pct_rows
    }

    # Per-floor category assignments (empty set for a floor = all cats active)
    from collections import defaultdict
    _assignments = FloorCategoryAssignment.objects.filter(block=block).values('floor_number', 'category_id')
    floor_assigned = defaultdict(set)
    for a in _assignments:
        floor_assigned[a['floor_number']].add(a['category_id'])

    floors = _build_floor_matrix(block, floor_cats, config, budget_map, asm_map, avr_pct_map, floor_assigned)

    land_works = []
    for cat in land_cats:
        lw, _ = LandscapingWork.objects.get_or_create(block=block, category=cat)
        land_works.append(lw)

    all_fws  = list(FloorWork.objects.filter(block=block))
    total_plan = sum(w.planned_amount for w in all_fws)
    total_fact = sum(w.fact_amount for w in all_fws)
    land_plan  = sum(w.planned_amount for w in land_works)
    land_fact  = sum(w.fact_amount for w in land_works)
    floor_budget_total = sum(fb.planned_amount for fb in budget_map.values())

    # AVR total amount — only accepted documents count as expense
    _avr_item_expr = ExpressionWrapper(
        F('items__quantity') * F('items__unit_price'),
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )
    avr_accepted_qs = AvrDocument.objects.filter(block=block, is_accepted=True)
    avr_grand_total = (avr_accepted_qs
                       .aggregate(total=Coalesce(Sum(_avr_item_expr), D0))['total'])
    # Use accepted_amount if set (overrides item sum)
    for _avr in avr_accepted_qs.filter(accepted_amount__isnull=False):
        pass  # accepted_amount is per-doc; sum below handles it
    avr_grand_total_manual = avr_accepted_qs.filter(
        accepted_amount__isnull=False).aggregate(s=Coalesce(Sum('accepted_amount'), D0))['s']
    avr_grand_total_items  = avr_accepted_qs.filter(
        accepted_amount__isnull=True).aggregate(s=Coalesce(Sum(_avr_item_expr), D0))['s']
    avr_grand_total = avr_grand_total_manual + avr_grand_total_items

    # Rework (переделки) — accepted AVRs with is_rework=True
    avr_rework_qs = avr_accepted_qs.filter(is_rework=True)
    avr_rework_manual = avr_rework_qs.filter(
        accepted_amount__isnull=False).aggregate(s=Coalesce(Sum('accepted_amount'), D0))['s']
    avr_rework_items  = avr_rework_qs.filter(
        accepted_amount__isnull=True).aggregate(s=Coalesce(Sum(_avr_item_expr), D0))['s']
    avr_rework_total  = avr_rework_manual + avr_rework_items

    # Overall building completion % — average display_pct across all floors
    building_pct = round(sum(f['display_pct'] for f in floors) / len(floors), 1) if floors else 0
    total_expenses = asm_grand_total + avr_grand_total

    # Recent documents: combine AsmDocument + AvrDocument, sorted by date
    _item_expr2 = ExpressionWrapper(
        F('items__quantity') * F('items__unit_price'),
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )
    recent_asms = list(
        AsmDocument.objects.filter(block=block)
        .annotate(doc_total=Coalesce(Sum(_item_expr2), D0))
        .select_related('category')
        .order_by('-doc_date', '-created_at')[:10]
    )
    recent_avrs = list(
        AvrDocument.objects.filter(block=block)
        .annotate(doc_total=Coalesce(
            Sum(ExpressionWrapper(F('items__quantity') * F('items__unit_price'),
                                  output_field=DecimalField(max_digits=15, decimal_places=2))),
            D0))
        .select_related('category')
        .order_by('-doc_date', '-created_at')[:10]
    )
    _all_docs = (
        [{'type': 'asm', 'doc': d, 'date': d.doc_date, 'created_at': d.created_at} for d in recent_asms] +
        [{'type': 'avr', 'doc': d, 'date': d.doc_date, 'created_at': d.created_at} for d in recent_avrs]
    )
    _all_docs.sort(key=lambda x: (x['date'], x['created_at']), reverse=True)
    recent_docs = _all_docs[:8]

    recent_acts = list(WorkAct.objects.filter(block=block).order_by('-act_date')[:5])

    unprice_docs = []
    if _is_admin_user(request.user):
        unprice_docs = list(
            AsmDocument.objects.filter(
                block=block,
                items__unit_price=0,
                items__quantity__gt=0,
            ).distinct()
            .select_related('category')
            .order_by('-doc_date')
        )

    # Works currently in progress — based on AVR completion_pct (0 < total < 100)
    cat_map = {cat.id: cat for cat in floor_cats}
    accepted_pairs = set(
        AvrDocument.objects.filter(block=block, is_accepted=True)
        .values_list('floor_number', 'category_id')
    )
    ongoing_works = []
    for (fn, cat_id), pct in avr_pct_map.items():
        if (fn, cat_id) in accepted_pairs:
            continue
        if 0 < pct < 100 and cat_id in cat_map:
            lbl = f'Подвал {abs(fn)}' if fn < 0 else f'Этаж {fn}'
            ongoing_works.append({
                'floor_label': lbl,
                'floor_number': fn,
                'category': cat_map[cat_id],
                'progress_pct': round(pct, 1),
            })
    ongoing_works.sort(key=lambda x: x['floor_number'])

    # Documents awaiting admin signature
    pending_avr = list(
        AvrDocument.objects.filter(block=block, is_accepted=False, completion_pct__gte=100)
        .select_related('category').order_by('-doc_date')
    )
    pending_asm = list(
        AsmDocument.objects.filter(block=block, is_accepted=False)
        .prefetch_related('items').select_related('category').order_by('-doc_date')
    )
    # Only show ASMs that have at least one item filled in
    pending_asm = [d for d in pending_asm if d.items.exists()]
    pending_docs = sorted(
        [{'doc': d, 'dtype': 'avr'} for d in pending_avr] +
        [{'doc': d, 'dtype': 'asm'} for d in pending_asm],
        key=lambda x: x['doc'].doc_date, reverse=True
    )

    return render(request, 'planfact/block.html', {
        'blk': block,
        'config': config,
        'floors': floors,
        'floor_cats': floor_cats,
        'land_works': land_works,
        'total_plan': total_plan,
        'total_fact': total_fact,
        'land_plan': land_plan,
        'land_fact': land_fact,
        'floor_budget_total': floor_budget_total,
        'asm_grand_total': asm_grand_total,
        'avr_grand_total': avr_grand_total,
        'avr_rework_total': avr_rework_total,
        'total_expenses': total_expenses,
        'building_pct': building_pct,
        'recent_docs': recent_docs,
        'recent_acts': recent_acts,
        'pending_docs': pending_docs,
        'is_admin': _is_admin_user(request.user),
        'unprice_docs': unprice_docs,
        'ongoing_works': ongoing_works,
    })


@production_required
def planfact_floor_edit(request, block_pk, floor_number):
    floor_number = int(floor_number)
    block = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    categories = list(WorkCategory.objects.filter(scope__in=['floor', 'general']))

    works = {}
    for cat in categories:
        fw, _ = FloorWork.objects.get_or_create(block=block, floor_number=floor_number, category=cat)
        works[cat.id] = fw

    if request.method == 'POST':
        for cat in categories:
            fw = works[cat.id]
            fw.planned_quantity = request.POST.get(f'plan_qty_{cat.id}') or 0
            fw.planned_amount   = request.POST.get(f'plan_amt_{cat.id}') or 0
            fw.fact_quantity    = request.POST.get(f'fact_qty_{cat.id}') or 0
            fw.fact_amount      = request.POST.get(f'fact_amt_{cat.id}') or 0
            fw.fact_date        = request.POST.get(f'fact_date_{cat.id}') or None
            fw.contractor       = request.POST.get(f'contractor_{cat.id}', '')
            fw.notes            = request.POST.get(f'notes_{cat.id}', '')
            fw.updated_by       = request.user
            fw.save()
        messages.success(request, f'Этаж {floor_number} сохранён.')
        return redirect('planfact_block', block_pk=block_pk)

    return render(request, 'planfact/floor_edit.html', {
        'blk': block,
        'floor_number': floor_number,
        'categories': categories,
        'works': works,
    })


@production_required
def planfact_landscaping_edit(request, block_pk):
    block = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    categories = list(WorkCategory.objects.filter(scope__in=['landscaping', 'general']))

    works = {}
    for cat in categories:
        lw, _ = LandscapingWork.objects.get_or_create(block=block, category=cat)
        works[cat.id] = lw

    if request.method == 'POST':
        for cat in categories:
            lw = works[cat.id]
            lw.planned_quantity = request.POST.get(f'plan_qty_{cat.id}') or 0
            lw.planned_amount   = request.POST.get(f'plan_amt_{cat.id}') or 0
            lw.fact_quantity    = request.POST.get(f'fact_qty_{cat.id}') or 0
            lw.fact_amount      = request.POST.get(f'fact_amt_{cat.id}') or 0
            lw.fact_date        = request.POST.get(f'fact_date_{cat.id}') or None
            lw.contractor       = request.POST.get(f'contractor_{cat.id}', '')
            lw.notes            = request.POST.get(f'notes_{cat.id}', '')
            lw.updated_by       = request.user
            lw.save()
        messages.success(request, 'Благоустройство сохранено.')
        return redirect('planfact_block', block_pk=block_pk)

    return render(request, 'planfact/landscaping_edit.html', {
        'blk': block,
        'categories': categories,
        'works': works,
    })


@production_required
def act_create(request, block_pk):
    block = get_object_or_404(Block, pk=block_pk)
    floor_works_qs = FloorWork.objects.filter(block=block, fact_amount__gt=0).select_related('category')
    land_works_qs  = LandscapingWork.objects.filter(block=block, fact_amount__gt=0).select_related('category')

    if request.method == 'POST':
        act_type   = request.POST.get('act_type', 'avr')
        act_number = request.POST.get('act_number', '').strip()
        act_date   = request.POST.get('act_date', '').strip()
        contractor = request.POST.get('contractor', '').strip()
        notes      = request.POST.get('notes', '').strip()
        fw_ids     = request.POST.getlist('floor_work_ids')
        lw_ids     = request.POST.getlist('land_work_ids')

        if not act_number or not act_date:
            messages.error(request, 'Укажите номер и дату акта.')
        else:
            fws   = FloorWork.objects.filter(pk__in=fw_ids)
            lws   = LandscapingWork.objects.filter(pk__in=lw_ids)
            total = sum(w.fact_amount for w in fws) + sum(w.fact_amount for w in lws)
            act   = WorkAct.objects.create(
                act_type=act_type, act_number=act_number, act_date=act_date,
                block=block, contractor=contractor, notes=notes,
                total_amount=total, created_by=request.user,
            )
            act.floor_works.set(fws)
            act.landscaping_works.set(lws)
            messages.success(request, f'Акт №{act_number} создан.')
            return redirect('act_print', pk=act.pk)

    return render(request, 'planfact/act_create.html', {
        'blk': block,
        'floor_works': floor_works_qs,
        'land_works': land_works_qs,
    })


@staff_required
def floor_category_edit(request, block_pk):
    block  = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    config, _ = BlockFloorConfig.objects.get_or_create(
        block=block, defaults={'total_floors': 16, 'underground_floors': 0}
    )
    cats = list(WorkCategory.objects.filter(scope__in=['floor', 'general']))
    underground = config.underground_floors
    above       = config.total_floors - underground
    floor_numbers = list(reversed(list(range(-underground, 0)) + list(range(1, above + 1))))

    # Current assignments: floor_number -> set of category_ids
    existing = set(
        FloorCategoryAssignment.objects.filter(block=block)
        .values_list('floor_number', 'category_id')
    )
    configured_floors = {fn for fn, _ in existing}

    if request.method == 'POST':
        FloorCategoryAssignment.objects.filter(block=block).delete()
        to_create = []
        for fn in floor_numbers:
            for cat in cats:
                if request.POST.get(f'assign_{fn}_{cat.id}'):
                    to_create.append(FloorCategoryAssignment(block=block, floor_number=fn, category=cat))
        FloorCategoryAssignment.objects.bulk_create(to_create)
        messages.success(request, 'Виды работ по этажам сохранены.')
        return redirect('planfact_block', block_pk=block_pk)

    rows = []
    for fn in floor_numbers:
        label = f'Подвал {abs(fn)}' if fn < 0 else f'Этаж {fn}'
        cats_data = []
        for cat in cats:
            if fn in configured_floors:
                is_active = (fn, cat.id) in existing
            else:
                is_active = True  # default: all active
            cats_data.append({'category': cat, 'is_active': is_active})
        rows.append({'number': fn, 'label': label, 'is_underground': fn < 0, 'cats': cats_data})

    return render(request, 'planfact/floor_category_edit.html', {
        'blk': block, 'rows': rows, 'cats': cats,
    })


@production_required
def progress_board(request, block_pk):
    from collections import defaultdict
    if not _can_access_block(request.user, block_pk):
        messages.error(request, 'Нет доступа к этому блоку.')
        return redirect('planfact_index')

    block  = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    config, _ = BlockFloorConfig.objects.get_or_create(
        block=block, defaults={'total_floors': 16, 'underground_floors': 0}
    )
    cats = list(WorkCategory.objects.filter(scope__in=['floor', 'general']).order_by('order', 'id'))

    underground = config.underground_floors
    above       = config.total_floors - underground
    floor_numbers = list(reversed(list(range(-underground, 0)) + list(range(1, above + 1))))

    works = {(w.floor_number, w.category_id): w
             for w in FloorWork.objects.filter(block=block, category__in=cats)}

    # AVR completion per floor+category — Max because each AVR shows cumulative state
    avr_agg = (AvrDocument.objects
               .filter(block=block)
               .values('floor_number', 'category_id')
               .annotate(total_pct=Max('completion_pct')))
    avr_pct_map = {(r['floor_number'], r['category_id']): float(r['total_pct'])
                   for r in avr_agg}

    # Which categories are assigned per floor
    floor_assigned = defaultdict(set)
    for a in FloorCategoryAssignment.objects.filter(block=block):
        floor_assigned[a.floor_number].add(a.category_id)
    all_cat_ids = {c.id for c in cats}

    if request.method == 'POST':
        for fn in floor_numbers:
            active_ids = floor_assigned[fn] if fn in floor_assigned else all_cat_ids
            for cat in cats:
                if cat.id not in active_ids:
                    continue
                # Skip AVR-sourced cells — those are managed via AVR documents
                if avr_pct_map.get((fn, cat.id), 0) > 0:
                    continue
                key = f'pct_{fn}_{cat.id}'
                val = request.POST.get(key, '').strip()
                if val == '':
                    continue
                try:
                    pct = max(0, min(100, int(val)))
                except ValueError:
                    continue
                fw = works.get((fn, cat.id))
                if fw is None:
                    fw = FloorWork(block=block, floor_number=fn, category=cat,
                                   planned_quantity=100, fact_quantity=0)
                if fw.planned_quantity == 0:
                    fw.planned_quantity = 100
                fw.fact_quantity = pct * fw.planned_quantity / 100
                fw.updated_by = request.user
                fw.save()
        messages.success(request, 'Прогресс сохранён.')
        return redirect('progress_board', block_pk=block_pk)

    rows = []
    for fn in floor_numbers:
        label = f'Подвал {abs(fn)}' if fn < 0 else f'Этаж {fn}'
        active_ids = floor_assigned[fn] if fn in floor_assigned else all_cat_ids
        cats_data = []
        for cat in cats:
            assigned  = cat.id in active_ids
            fw        = works.get((fn, cat.id))
            fw_pct    = fw.progress_pct if fw else 0
            avr_pct   = avr_pct_map.get((fn, cat.id), 0)
            pct       = avr_pct if avr_pct > 0 else fw_pct
            source    = 'avr' if avr_pct > 0 else 'manual'
            cats_data.append({
                'category': cat,
                'pct':      pct,
                'avr_pct':  avr_pct,
                'fw_pct':   fw_pct,
                'source':   source,
                'assigned': assigned,
            })
        active_cats = [c for c in cats_data if c['assigned']]
        floor_avg = round(sum(c['pct'] for c in active_cats) / len(active_cats), 0) if active_cats else 0
        rows.append({
            'number':       fn,
            'label':        label,
            'is_underground': fn < 0,
            'cats':         cats_data,
            'avg_pct':      int(floor_avg),
        })

    return render(request, 'planfact/progress_board.html', {
        'blk':      block,
        'rows':     rows,
        'cats':     cats,
        'is_admin': _is_admin_user(request.user),
    })


@production_required
def progress_board_excel(request, block_pk):
    import io
    from collections import defaultdict
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse

    if not _can_access_block(request.user, block_pk):
        messages.error(request, 'Нет доступа.')
        return redirect('planfact_index')

    block  = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    config, _ = BlockFloorConfig.objects.get_or_create(
        block=block, defaults={'total_floors': 16, 'underground_floors': 0}
    )
    cats = list(WorkCategory.objects.filter(scope__in=['floor', 'general']).order_by('order', 'id'))

    underground = config.underground_floors
    above       = config.total_floors - underground
    floor_numbers = list(reversed(list(range(-underground, 0)) + list(range(1, above + 1))))

    works = {(w.floor_number, w.category_id): w
             for w in FloorWork.objects.filter(block=block, category__in=cats)}

    avr_agg = (AvrDocument.objects.filter(block=block)
               .values('floor_number', 'category_id')
               .annotate(total_pct=Max('completion_pct')))
    avr_pct_map = {(r['floor_number'], r['category_id']): float(r['total_pct'])
                   for r in avr_agg}

    floor_assigned = defaultdict(set)
    for a in FloorCategoryAssignment.objects.filter(block=block):
        floor_assigned[a.floor_number].add(a.category_id)
    all_cat_ids = {c.id for c in cats}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f'Блок {block.name}'

    thin = Side(style='thin', color='CBD5E1')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def fill(hex_color):
        return PatternFill('solid', fgColor=hex_color.lstrip('#'))

    def pct_fill(p):
        if p >= 100: return fill('#22c55e')
        if p >= 67:  return fill('#4ade80')
        if p >= 34:  return fill('#86efac')
        if p > 0:    return fill('#fef9c3')
        return PatternFill()

    def pct_font_color(p):
        return '155724' if p >= 100 else ('166534' if p > 0 else '94A3B8')

    # ── Header row 1: title ──
    ws.merge_cells(f'A1:{get_column_letter(len(cats) + 2)}1')
    c = ws['A1']
    c.value = f'Ход строительства — {block.residential_complex.name} / Блок {block.name}'
    c.font = Font(bold=True, size=13)
    c.alignment = Alignment(horizontal='center', vertical='center')
    c.fill = fill('#1e293b')
    c.font = Font(bold=True, size=13, color='F1F5F9')
    ws.row_dimensions[1].height = 28

    # ── Header row 2: columns ──
    ws.cell(row=2, column=1, value='Этаж').font = Font(bold=True, color='F1F5F9')
    ws.cell(row=2, column=1).fill = fill('#334155')
    ws.cell(row=2, column=1).alignment = Alignment(horizontal='center', vertical='center')
    for i, cat in enumerate(cats, start=2):
        c = ws.cell(row=2, column=i, value=cat.name)
        c.font = Font(bold=True, color='F1F5F9', size=9)
        c.fill = fill('#334155')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = border
        ws.column_dimensions[get_column_letter(i)].width = 14
    avg_col = len(cats) + 2
    ws.cell(row=2, column=avg_col, value='Итого').font = Font(bold=True, color='F1F5F9')
    ws.cell(row=2, column=avg_col).fill = fill('#0f172a')
    ws.cell(row=2, column=avg_col).alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[2].height = 36
    ws.column_dimensions['A'].width = 16
    ws.column_dimensions[get_column_letter(avg_col)].width = 10

    # ── Data rows ──
    for row_idx, fn in enumerate(floor_numbers, start=3):
        label = f'Подвал {abs(fn)}' if fn < 0 else f'Этаж {fn}'
        active_ids = floor_assigned[fn] if fn in floor_assigned else all_cat_ids

        lbl_cell = ws.cell(row=row_idx, column=1, value=label)
        lbl_cell.font = Font(bold=True, size=10)
        lbl_cell.fill = fill('#f1f5f9') if fn < 0 else fill('#ffffff')
        lbl_cell.alignment = Alignment(horizontal='left', vertical='center', indent=1)
        lbl_cell.border = border

        active_pcts = []
        for col_idx, cat in enumerate(cats, start=2):
            assigned = cat.id in active_ids
            avr_pct  = avr_pct_map.get((fn, cat.id), 0)
            fw       = works.get((fn, cat.id))
            fw_pct   = fw.progress_pct if fw else 0
            pct      = avr_pct if avr_pct > 0 else fw_pct

            dc = ws.cell(row=row_idx, column=col_idx)
            dc.border = border
            dc.alignment = Alignment(horizontal='center', vertical='center')

            if not assigned:
                dc.value = '—'
                dc.font = Font(color='CBD5E1')
                dc.fill = fill('#f8fafc')
            else:
                source = ' (АВР)' if avr_pct > 0 else ''
                dc.value = f'{int(pct)}%{source}'
                dc.font = Font(bold=True, color=pct_font_color(pct), size=11)
                dc.fill = pct_fill(pct)
                active_pcts.append(pct)

        avg = round(sum(active_pcts) / len(active_pcts), 0) if active_pcts else 0
        ac = ws.cell(row=row_idx, column=avg_col, value=f'{int(avg)}%')
        ac.font = Font(bold=True, color=pct_font_color(avg), size=11)
        ac.fill = pct_fill(avg)
        ac.alignment = Alignment(horizontal='center', vertical='center')
        ac.border = border
        ws.row_dimensions[row_idx].height = 22

    ws.freeze_panes = 'B3'

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f'progress_{block.name}_{date.today()}.xlsx'
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    return response


@production_required
def act_print(request, pk):
    act = get_object_or_404(
        WorkAct.objects.select_related('block', 'block__residential_complex', 'created_by')
        .prefetch_related('floor_works__category', 'landscaping_works__category'),
        pk=pk,
    )
    return render(request, 'planfact/act_print.html', {'act': act})


@production_required
def floor_budget_edit(request, block_pk):
    block  = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    config, _ = BlockFloorConfig.objects.get_or_create(
        block=block, defaults={'total_floors': 16, 'underground_floors': 0}
    )
    underground = config.underground_floors
    above       = config.total_floors - underground
    floor_numbers = list(range(-underground, 0)) + list(range(1, above + 1))

    budget_map = {fb.floor_number: fb for fb in FloorBudget.objects.filter(block=block)}

    if request.method == 'POST':
        for fn in floor_numbers:
            amt   = request.POST.get(f'plan_{fn}', '0') or '0'
            notes = request.POST.get(f'notes_{fn}', '')
            fb, _ = FloorBudget.objects.get_or_create(block=block, floor_number=fn)
            fb.planned_amount = amt
            fb.notes          = notes
            fb.save()
        messages.success(request, 'Плановые бюджеты по этажам сохранены.')
        return redirect('planfact_block', block_pk=block_pk)

    rows = []
    for fn in reversed(floor_numbers):
        fb = budget_map.get(fn)
        rows.append({
            'number': fn,
            'label': f'Подвал {abs(fn)}' if fn < 0 else f'Этаж {fn}',
            'planned_amount': fb.planned_amount if fb else 0,
            'notes': fb.notes if fb else '',
        })

    return render(request, 'planfact/floor_budget_edit.html', {
        'blk': block, 'rows': rows,
    })


@production_required
def act_list(request, block_pk):
    block = get_object_or_404(Block, pk=block_pk)
    acts  = WorkAct.objects.filter(block=block).order_by('-act_date')
    return render(request, 'planfact/act_list.html', {'blk': block, 'acts': acts})


# ─── ASM (Акт списания материалов) views ────────────────────────────────────

@production_required
def asm_list(request, block_pk, floor_number, category_id):
    if not _can_access_block(request.user, block_pk):
        messages.error(request, 'Нет доступа к этому блоку.')
        return redirect('planfact_index')
    floor_number = int(floor_number)
    blk      = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    category = get_object_or_404(WorkCategory, pk=category_id)
    docs     = AsmDocument.objects.filter(
        block=blk, floor_number=floor_number, category=category
    ).prefetch_related('items')
    floor_label = f'Подвал {abs(floor_number)}' if floor_number < 0 else f'Этаж {floor_number}'
    return render(request, 'planfact/asm_list.html', {
        'blk': blk, 'category': category,
        'floor_number': floor_number, 'floor_label': floor_label,
        'docs': docs,
        'is_admin': _is_admin_user(request.user),
    })


@production_required
def asm_create(request, block_pk, floor_number, category_id):
    if not _can_access_block(request.user, block_pk):
        messages.error(request, 'Нет доступа к этому блоку.')
        return redirect('planfact_index')
    floor_number = int(floor_number)
    blk      = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    category = get_object_or_404(WorkCategory, pk=category_id)
    floor_label = f'Подвал {abs(floor_number)}' if floor_number < 0 else f'Этаж {floor_number}'

    if request.method == 'POST':
        doc_number      = request.POST.get('doc_number', '').strip()
        doc_date        = request.POST.get('doc_date', '')
        description     = request.POST.get('description', '').strip()
        head_warehouse  = request.POST.get('head_warehouse', '').strip()
        head_section    = request.POST.get('head_section', '').strip()
        head_accounting = request.POST.get('head_accounting', '').strip()
        head_production = request.POST.get('head_production', '').strip()
        if not doc_date:
            messages.error(request, 'Укажите дату акта.')
        else:
            doc = AsmDocument.objects.create(
                block=blk, floor_number=floor_number, category=category,
                doc_number=doc_number, doc_date=doc_date,
                description=description,
                head_warehouse=head_warehouse, head_section=head_section,
                head_accounting=head_accounting, head_production=head_production,
                created_by=request.user,
            )
            messages.success(request, 'АСМ создан. Добавьте материалы.')
            return redirect('asm_edit', asm_pk=doc.pk)

    from datetime import date as _date
    return render(request, 'planfact/asm_create.html', {
        'blk': blk, 'category': category,
        'floor_number': floor_number, 'floor_label': floor_label,
        'today': _date.today(),
    })


@production_required
def asm_edit(request, asm_pk):
    doc = get_object_or_404(
        AsmDocument.objects.select_related('block', 'block__residential_complex', 'category')
                           .prefetch_related('items'),
        pk=asm_pk,
    )
    if not _can_access_block(request.user, doc.block_id):
        messages.error(request, 'Нет доступа к этому блоку.')
        return redirect('planfact_index')

    is_admin = _is_admin_user(request.user)
    items = list(doc.items.all())

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        if action == 'accept' and is_admin and not doc.is_accepted:
            doc.is_accepted     = True
            doc.accepted_by     = request.POST.get('accepted_by', '').strip()
            doc.accepted_at     = request.POST.get('accepted_at') or date.today()
            raw_amt = request.POST.get('accepted_amount', '').strip().replace(' ', '')
            doc.accepted_amount = Decimal(raw_amt) if raw_amt else doc.total_amount
            doc.save()
            messages.success(request, 'АСМ принят и заблокирован.')
            return redirect('asm_edit', asm_pk=doc.pk)

        if doc.is_accepted:
            messages.error(request, 'АСМ принят и заблокирован — изменения запрещены.')
            return redirect('asm_edit', asm_pk=doc.pk)

        doc.doc_number      = request.POST.get('doc_number', doc.doc_number).strip()
        doc.doc_date        = request.POST.get('doc_date', str(doc.doc_date))
        doc.description     = request.POST.get('description', doc.description).strip()
        doc.head_warehouse  = request.POST.get('head_warehouse', doc.head_warehouse).strip()
        doc.head_section    = request.POST.get('head_section', doc.head_section).strip()
        doc.head_accounting = request.POST.get('head_accounting', doc.head_accounting).strip()
        doc.head_production = request.POST.get('head_production', doc.head_production).strip()
        doc.save()

        delete_ids = request.POST.getlist('delete_item')
        if delete_ids:
            AsmItem.objects.filter(pk__in=delete_ids, document=doc).delete()

        for item in items:
            if str(item.pk) in delete_ids:
                continue
            name = request.POST.get(f'name_{item.pk}', '').strip()
            if name:
                item.name     = name
                item.unit     = request.POST.get(f'unit_{item.pk}', item.unit).strip()
                item.quantity = request.POST.get(f'qty_{item.pk}', '0') or 0
                item.unit_price = request.POST.get(f'price_{item.pk}', '0') or 0
                item.notes    = request.POST.get(f'notes_{item.pk}', '').strip()
                item.save()

        new_names  = request.POST.getlist('new_name')
        new_units  = request.POST.getlist('new_unit')
        new_qtys   = request.POST.getlist('new_qty')
        new_prices = request.POST.getlist('new_price')
        new_notes  = request.POST.getlist('new_notes')
        max_order  = max((i.order for i in items), default=0)
        for i, name in enumerate(new_names):
            name = name.strip()
            if not name:
                continue
            max_order += 1
            AsmItem.objects.create(
                document=doc, order=max_order,
                name=name,
                unit=(new_units[i] if i < len(new_units) else '').strip(),
                quantity=new_qtys[i] if i < len(new_qtys) and new_qtys[i] else 0,
                unit_price=(new_prices[i] if i < len(new_prices) and new_prices[i] else 0),
                notes=(new_notes[i] if i < len(new_notes) else '').strip(),
            )

        if action == 'save_print':
            return redirect('asm_print', asm_pk=doc.pk)
        messages.success(request, 'АСМ сохранён.')
        return redirect('asm_edit', asm_pk=doc.pk)

    EMPTY_ROWS = 8
    floor_label = f'Подвал {abs(doc.floor_number)}' if doc.floor_number < 0 else f'Этаж {doc.floor_number}'
    return render(request, 'planfact/asm_edit.html', {
        'doc': doc, 'items': items,
        'blk': doc.block, 'floor_label': floor_label,
        'empty_rows': range(EMPTY_ROWS),
        'is_admin': is_admin,
        'photos': doc.photos.all() if hasattr(doc, 'photos') else [],
    })


@production_required
def asm_print(request, asm_pk):
    doc = get_object_or_404(
        AsmDocument.objects.select_related('block', 'block__residential_complex', 'category')
                           .prefetch_related('items'),
        pk=asm_pk,
    )
    floor_label = f'Подвал {abs(doc.floor_number)}' if doc.floor_number < 0 else f'Этаж {doc.floor_number}'
    return render(request, 'planfact/asm_print.html', {'doc': doc, 'floor_label': floor_label})


@production_required
def asm_delete(request, asm_pk):
    doc = get_object_or_404(AsmDocument, pk=asm_pk)
    blk_pk      = doc.block_id
    floor_number = doc.floor_number
    cat_id      = doc.category_id
    if request.method == 'POST':
        if doc.is_accepted:
            messages.error(request, 'Принятый АСМ нельзя удалить.')
        else:
            doc.delete()
            messages.success(request, 'АСМ удалён.')
        return redirect('asm_list', block_pk=blk_pk, floor_number=floor_number, category_id=cat_id)
    return redirect('asm_list', block_pk=blk_pk, floor_number=floor_number, category_id=cat_id)


# ─── Calendar Plan views ────────────────────────────────────────────────────

@production_required
def calendar_plan_list(request, block_pk):
    blk   = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    plans = CalendarPlan.objects.filter(block=blk).order_by('-created_at')
    return render(request, 'planfact/calendar_plan_list.html', {'blk': blk, 'plans': plans})


@production_required
def calendar_plan_create(request, block_pk):
    blk = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    if request.method == 'POST':
        name        = request.POST.get('name', '').strip()
        start_year  = int(request.POST.get('start_year',  2023) or 2023)
        start_month = int(request.POST.get('start_month', 1)    or 1)
        end_year    = int(request.POST.get('end_year',    2025) or 2025)
        end_month   = int(request.POST.get('end_month',   12)   or 12)
        if not name:
            messages.error(request, 'Укажите название плана.')
        elif (start_year, start_month) > (end_year, end_month):
            messages.error(request, 'Дата начала должна быть раньше даты окончания.')
        else:
            plan = CalendarPlan.objects.create(
                block=blk, name=name,
                start_year=start_year, start_month=start_month,
                end_year=end_year, end_month=end_month,
                created_by=request.user,
            )
            messages.success(request, 'План создан. Добавьте задачи.')
            return redirect('calendar_task_edit', plan_pk=plan.pk)
    months = [(i, MONTHS_RU[i]) for i in range(1, 13)]
    years  = list(range(2020, 2035))
    return render(request, 'planfact/calendar_plan_create.html', {
        'blk': blk, 'months': months, 'years': years,
    })


@production_required
def calendar_plan_detail(request, plan_pk):
    plan = get_object_or_404(
        CalendarPlan.objects.select_related('block', 'block__residential_complex'),
        pk=plan_pk,
    )
    today       = date.today()
    month_range = plan.month_range()
    tasks       = list(plan.tasks.all())

    mp_map = {}
    for mp in CalendarMonthPlan.objects.filter(task__plan=plan):
        mp_map[(mp.task_id, mp.year, mp.month)] = mp

    D0 = Decimal('0')

    rows = []
    for task in tasks:
        cells           = []
        task_plan_total = D0
        task_fact_total = D0
        for (y, m) in month_range:
            mp        = mp_map.get((task.id, y, m))
            plan_amt  = mp.planned_amount if mp else D0
            fact_amt  = mp.fact_amount    if mp else D0
            task_plan_total += plan_amt
            task_fact_total += fact_amt
            is_current = (y == today.year and m == today.month)
            is_past    = (y, m) < (today.year, today.month)
            is_overdue = is_past and plan_amt > 0 and fact_amt < plan_amt
            is_done    = plan_amt > 0 and fact_amt >= plan_amt
            cells.append({
                'year': y, 'month': m,
                'plan_amt': plan_amt, 'fact_amt': fact_amt,
                'mp': mp,
                'is_current': is_current,
                'is_past': is_past,
                'is_overdue': is_overdue,
                'is_done': is_done,
            })
        rows.append({
            'task': task,
            'cells': cells,
            'plan_total': task_plan_total,
            'fact_total': task_fact_total,
        })

    col_totals = []
    for (y, m) in month_range:
        cp = sum((mp_map.get((t.id, y, m)).planned_amount if mp_map.get((t.id, y, m)) else D0) for t in tasks)
        cf = sum((mp_map.get((t.id, y, m)).fact_amount    if mp_map.get((t.id, y, m)) else D0) for t in tasks)
        col_totals.append({'year': y, 'month': m, 'plan': cp, 'fact': cf})

    month_headers = [(y, m, MONTHS_SHORT[m]) for (y, m) in month_range]

    return render(request, 'planfact/calendar_plan_detail.html', {
        'blk': plan.block,
        'plan': plan,
        'rows': rows,
        'month_headers': month_headers,
        'col_totals': col_totals,
        'today': today,
    })


@production_required
def calendar_task_edit(request, plan_pk):
    plan  = get_object_or_404(CalendarPlan.objects.select_related('block'), pk=plan_pk)
    tasks = list(plan.tasks.all())

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'add_task':
            name = request.POST.get('name', '').strip()
            unit = request.POST.get('unit', '').strip()
            if name:
                max_order = plan.tasks.aggregate(m=Max('order'))['m'] or 0
                CalendarTask.objects.create(plan=plan, name=name, unit=unit, order=max_order + 1)
                messages.success(request, f'Задача «{name}» добавлена.')
            else:
                messages.error(request, 'Укажите название задачи.')
        elif action == 'delete_task':
            task_id = request.POST.get('task_id')
            CalendarTask.objects.filter(pk=task_id, plan=plan).delete()
            messages.success(request, 'Задача удалена.')
        return redirect('calendar_task_edit', plan_pk=plan_pk)

    return render(request, 'planfact/calendar_task_edit.html', {
        'blk': plan.block, 'plan': plan, 'tasks': tasks,
    })


@production_required
def calendar_fact_enter(request, plan_pk):
    plan  = get_object_or_404(CalendarPlan.objects.select_related('block'), pk=plan_pk)
    today = date.today()
    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))

    tasks      = list(plan.tasks.all())
    month_plans = {mp.task_id: mp for mp in
                   CalendarMonthPlan.objects.filter(task__plan=plan, year=year, month=month)}

    if request.method == 'POST':
        for task in tasks:
            plan_amt = request.POST.get(f'plan_{task.id}', '0') or '0'
            fact_amt = request.POST.get(f'fact_{task.id}', '0') or '0'
            notes    = request.POST.get(f'notes_{task.id}', '')
            mp, _    = CalendarMonthPlan.objects.get_or_create(
                task=task, year=year, month=month,
                defaults={'planned_amount': 0, 'fact_amount': 0},
            )
            mp.planned_amount = plan_amt
            mp.fact_amount    = fact_amt
            mp.notes          = notes
            mp.updated_by     = request.user
            mp.save()
        messages.success(request, f'Данные за {MONTHS_RU[month]} {year} сохранены.')
        return redirect('calendar_plan_detail', plan_pk=plan_pk)

    D0   = Decimal('0')
    rows = []
    for task in tasks:
        mp = month_plans.get(task.id)
        rows.append({
            'task':     task,
            'plan_amt': mp.planned_amount if mp else D0,
            'fact_amt': mp.fact_amount    if mp else D0,
            'notes':    mp.notes          if mp else '',
        })

    prev_m, prev_y = (month - 1, year) if month > 1 else (12, year - 1)
    next_m, next_y = (month + 1, year) if month < 12 else (1,  year + 1)
    month_range    = plan.month_range()

    return render(request, 'planfact/calendar_fact_enter.html', {
        'blk': plan.block, 'plan': plan,
        'year': year, 'month': month, 'month_name': MONTHS_RU[month],
        'rows': rows,
        'prev_y': prev_y, 'prev_m': prev_m,
        'next_y': next_y, 'next_m': next_m,
        'in_range': (year, month) in month_range,
    })


@production_required
def calendar_plan_delete(request, plan_pk):
    plan     = get_object_or_404(CalendarPlan.objects.select_related('block'), pk=plan_pk)
    block_pk = plan.block_id
    if request.method == 'POST':
        plan.delete()
        messages.success(request, 'Календарный план удалён.')
        return redirect('calendar_plan_list', block_pk=block_pk)
    return render(request, 'planfact/calendar_plan_confirm_delete.html', {
        'blk': plan.block, 'plan': plan,
    })


# ─── AVR (Акт выполненных работ) views ──────────────────────────────────────

@production_required
def avr_list(request, block_pk, floor_number, category_id):
    if not _can_access_block(request.user, block_pk):
        messages.error(request, 'Нет доступа к этому блоку.')
        return redirect('planfact_index')
    floor_number = int(floor_number)
    blk      = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    category = get_object_or_404(WorkCategory, pk=category_id)
    docs     = AvrDocument.objects.filter(block=blk, floor_number=floor_number, category=category).prefetch_related('items')
    floor_label = f'Подвал {abs(floor_number)}' if floor_number < 0 else f'Этаж {floor_number}'
    try:
        fw = FloorWork.objects.get(block=blk, floor_number=floor_number, category=category)
        current_progress = fw.progress_pct
    except FloorWork.DoesNotExist:
        current_progress = 0
    return render(request, 'planfact/avr_list.html', {
        'blk': blk, 'category': category,
        'floor_number': floor_number, 'floor_label': floor_label,
        'docs': docs, 'is_admin': _is_admin_user(request.user),
        'current_progress': current_progress,
    })


@production_required
def avr_create(request, block_pk, floor_number, category_id):
    if not _can_access_block(request.user, block_pk):
        messages.error(request, 'Нет доступа.')
        return redirect('planfact_index')
    floor_number = int(floor_number)
    blk      = get_object_or_404(Block.objects.select_related('residential_complex'), pk=block_pk)
    category = get_object_or_404(WorkCategory, pk=category_id)
    floor_label = f'Подвал {abs(floor_number)}' if floor_number < 0 else f'Этаж {floor_number}'
    try:
        fw = FloorWork.objects.get(block=blk, floor_number=floor_number, category=category)
        current_progress = fw.progress_pct
    except FloorWork.DoesNotExist:
        current_progress = 0

    if request.method == 'POST':
        doc_number      = request.POST.get('doc_number', '').strip()
        doc_date        = request.POST.get('doc_date', '')
        contractor      = request.POST.get('contractor', '').strip()
        executor        = request.POST.get('executor', '').strip()
        completion_pct  = request.POST.get('completion_pct', '100') or '100'
        head_production = request.POST.get('head_production', '').strip()
        head_section    = request.POST.get('head_section', '').strip()
        foreman         = request.POST.get('foreman', '').strip()
        master          = request.POST.get('master', '').strip()
        executor_sign   = request.POST.get('executor_sign', '').strip()
        if not doc_date:
            messages.error(request, 'Укажите дату акта.')
        else:
            doc = AvrDocument.objects.create(
                block=blk, floor_number=floor_number, category=category,
                doc_number=doc_number, doc_date=doc_date,
                contractor=contractor, executor=executor,
                completion_pct=completion_pct,
                head_production=head_production, head_section=head_section,
                foreman=foreman, master=master, executor_sign=executor_sign,
                is_rework=request.POST.get('is_rework') == '1',
                created_by=request.user,
            )
            messages.success(request, 'АВР создан. Добавьте работы.')
            return redirect('avr_edit', avr_pk=doc.pk)

    from datetime import date as _date
    return render(request, 'planfact/avr_create.html', {
        'blk': blk, 'category': category,
        'floor_number': floor_number, 'floor_label': floor_label,
        'today': _date.today(),
        'current_progress': current_progress,
    })


@production_required
def avr_edit(request, avr_pk):
    doc = get_object_or_404(
        AvrDocument.objects.select_related('block', 'block__residential_complex', 'category').prefetch_related('items'),
        pk=avr_pk,
    )
    if not _can_access_block(request.user, doc.block_id):
        messages.error(request, 'Нет доступа.')
        return redirect('planfact_index')
    is_admin = _is_admin_user(request.user)
    items = list(doc.items.all())

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        # Photo upload
        if action == 'upload_photo':
            for f in request.FILES.getlist('photos'):
                AvrPhoto.objects.create(document=doc, image=f,
                                        caption=request.POST.get('caption', '').strip())
            return redirect('avr_edit', avr_pk=doc.pk)

        # Photo delete
        if action == 'delete_photo':
            AvrPhoto.objects.filter(pk=request.POST.get('photo_pk'), document=doc).delete()
            return redirect('avr_edit', avr_pk=doc.pk)

        # Accept action — admin only, locks the document
        if action == 'accept' and is_admin and not doc.is_accepted:
            doc.is_accepted     = True
            doc.accepted_by     = request.POST.get('accepted_by', '').strip()
            doc.accepted_at     = request.POST.get('accepted_at') or date.today()
            raw_amt = request.POST.get('accepted_amount', '').strip().replace(' ', '')
            doc.accepted_amount = Decimal(raw_amt) if raw_amt else doc.total_amount
            doc.save()
            messages.success(request, 'АВР принят и заблокирован.')
            return redirect('avr_edit', avr_pk=doc.pk)

        # Block all edits once accepted
        if doc.is_accepted:
            messages.error(request, 'АВР принят и заблокирован — изменения запрещены.')
            return redirect('avr_edit', avr_pk=doc.pk)

        doc.doc_number      = request.POST.get('doc_number', doc.doc_number).strip()
        doc.doc_date        = request.POST.get('doc_date', str(doc.doc_date))
        doc.contractor      = request.POST.get('contractor', doc.contractor).strip()
        doc.executor        = request.POST.get('executor', doc.executor).strip()
        doc.completion_pct  = request.POST.get('completion_pct', doc.completion_pct) or doc.completion_pct
        doc.status          = request.POST.get('status', doc.status)
        doc.defects             = request.POST.get('defects', doc.defects).strip()
        doc.defect_deadline     = request.POST.get('defect_deadline', doc.defect_deadline).strip()
        doc.safety_compliance   = request.POST.get('safety_compliance', doc.safety_compliance).strip()
        doc.deadline_compliance = request.POST.get('deadline_compliance', doc.deadline_compliance).strip()
        doc.head_production = request.POST.get('head_production', doc.head_production).strip()
        doc.head_section    = request.POST.get('head_section', doc.head_section).strip()
        doc.foreman         = request.POST.get('foreman', doc.foreman).strip()
        doc.master          = request.POST.get('master', doc.master).strip()
        doc.executor_sign   = request.POST.get('executor_sign', doc.executor_sign).strip()
        doc.is_rework       = request.POST.get('is_rework') == '1'
        doc.save()

        delete_ids = request.POST.getlist('delete_item')
        if delete_ids:
            AvrItem.objects.filter(pk__in=delete_ids, document=doc).delete()

        for item in items:
            if str(item.pk) in delete_ids:
                continue
            name = request.POST.get(f'name_{item.pk}', '').strip()
            if name:
                item.name     = name
                item.unit     = request.POST.get(f'unit_{item.pk}', item.unit).strip()
                item.quantity = request.POST.get(f'qty_{item.pk}', '0') or 0
                item.unit_price = request.POST.get(f'price_{item.pk}', '0') or 0
                item.notes    = request.POST.get(f'notes_{item.pk}', '').strip()
                item.save()

        new_names  = request.POST.getlist('new_name')
        new_units  = request.POST.getlist('new_unit')
        new_qtys   = request.POST.getlist('new_qty')
        new_prices = request.POST.getlist('new_price')
        new_notes  = request.POST.getlist('new_notes')
        max_order  = max((i.order for i in items), default=0)
        for i, name in enumerate(new_names):
            name = name.strip()
            if not name:
                continue
            max_order += 1
            AvrItem.objects.create(
                document=doc, order=max_order, name=name,
                unit=(new_units[i] if i < len(new_units) else '').strip(),
                quantity=new_qtys[i] if i < len(new_qtys) and new_qtys[i] else 0,
                unit_price=(new_prices[i] if i < len(new_prices) and new_prices[i] else 0),
                notes=(new_notes[i] if i < len(new_notes) else '').strip(),
            )

        if action == 'save_print':
            return redirect('avr_print', avr_pk=doc.pk)
        messages.success(request, 'АВР сохранён.')
        return redirect('avr_edit', avr_pk=doc.pk)

    EMPTY_ROWS = 8
    floor_label = (f'Подвал {abs(doc.floor_number)}' if doc.floor_number and doc.floor_number < 0
                   else (f'Этаж {doc.floor_number}' if doc.floor_number else 'Общий'))
    return render(request, 'planfact/avr_edit.html', {
        'doc': doc, 'items': items,
        'blk': doc.block, 'floor_label': floor_label,
        'empty_rows': range(EMPTY_ROWS),
        'is_admin': is_admin,
        'photos': doc.photos.all(),
    })


@production_required
def avr_print(request, avr_pk):
    doc = get_object_or_404(
        AvrDocument.objects.select_related('block', 'block__residential_complex', 'category').prefetch_related('items'),
        pk=avr_pk,
    )
    items_count = doc.items.count()
    empty_rows = range(max(0, 7 - items_count))
    floor_label = (f'Подвал {abs(doc.floor_number)}' if doc.floor_number and doc.floor_number < 0
                   else (f'Этаж {doc.floor_number}' if doc.floor_number else ''))
    return render(request, 'planfact/avr_print.html', {'doc': doc, 'floor_label': floor_label, 'empty_rows': empty_rows})


@production_required
def avr_delete(request, avr_pk):
    doc = get_object_or_404(AvrDocument, pk=avr_pk)
    blk_pk       = doc.block_id
    floor_number = doc.floor_number
    cat_id       = doc.category_id
    if request.method == 'POST':
        if doc.is_accepted:
            messages.error(request, 'Принятый АВР нельзя удалить.')
        else:
            doc.delete()
            messages.success(request, 'АВР удалён.')
        return redirect('avr_list', block_pk=blk_pk, floor_number=floor_number, category_id=cat_id)
    return redirect('avr_list', block_pk=blk_pk, floor_number=floor_number, category_id=cat_id)


# ─── Builder user management (staff only) ───────────────────────────────────

@staff_required
def manage_users(request):
    builders = (User.objects.filter(is_staff=False, is_superuser=False)
                .prefetch_related('block_accesses__block__residential_complex')
                .order_by('username'))
    return render(request, 'planfact/manage_users.html', {'builders': builders})


@staff_required
def manage_user_create(request):
    all_blocks = Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name')
    if request.method == 'POST':
        username   = request.POST.get('username', '').strip()
        password   = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        block_ids  = request.POST.getlist('blocks')
        error = None
        if not username or not password:
            error = 'Укажите логин и пароль.'
        elif User.objects.filter(username=username).exists():
            error = f'Пользователь «{username}» уже существует.'
        if error:
            messages.error(request, error)
        else:
            user = User.objects.create_user(
                username=username, password=password,
                first_name=first_name, last_name=last_name,
            )
            for bid in block_ids:
                BlockAccess.objects.create(user=user, block_id=bid)
            messages.success(request, f'Строитель «{username}» создан.')
            return redirect('manage_users')
    return render(request, 'planfact/manage_user_create.html', {'all_blocks': all_blocks})


@staff_required
def manage_user_edit(request, user_pk):
    builder    = get_object_or_404(User, pk=user_pk, is_staff=False, is_superuser=False)
    all_blocks = Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name')
    current_ids = set(BlockAccess.objects.filter(user=builder).values_list('block_id', flat=True))

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'save_blocks':
            new_ids = set(int(x) for x in request.POST.getlist('blocks'))
            BlockAccess.objects.filter(user=builder).exclude(block_id__in=new_ids).delete()
            for bid in new_ids:
                BlockAccess.objects.get_or_create(user=builder, block_id=bid)
            current_ids = new_ids
            messages.success(request, 'Доступ к блокам обновлён.')
        elif action == 'reset_password':
            new_pwd = request.POST.get('new_password', '').strip()
            if new_pwd:
                builder.set_password(new_pwd)
                builder.save()
                messages.success(request, 'Пароль изменён.')
            else:
                messages.error(request, 'Введите новый пароль.')
        elif action == 'delete_user':
            name = builder.username
            builder.delete()
            messages.success(request, f'Пользователь «{name}» удалён.')
            return redirect('manage_users')
        return redirect('manage_user_edit', user_pk=builder.pk)

    return render(request, 'planfact/manage_user_edit.html', {
        'builder': builder,
        'all_blocks': all_blocks,
        'current_ids': current_ids,
    })
