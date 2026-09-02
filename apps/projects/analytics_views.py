import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Q, Count
from django.db.models.functions import Coalesce
from django.db.models import Value

from .models import ResidentialComplex, Block, FloorExpense


def analytics_index(request):
    rc = ResidentialComplex.objects.order_by('name').first()
    if rc:
        return redirect('rc_analytics', pk=rc.pk)
    return render(request, 'analytics/no_data.html', {})


def rc_analytics(request, pk):
    rc = get_object_or_404(ResidentialComplex, pk=pk)
    all_rcs = list(ResidentialComplex.objects.order_by('name'))
    all_blocks = list(Block.objects.filter(residential_complex=rc).order_by('name'))

    date_from = request.GET.get('date_from', '').strip()
    date_to   = request.GET.get('date_to', '').strip()
    block_filter = request.GET.get('block', '').strip()

    selected_block = None
    if block_filter and block_filter.isdigit():
        selected_block = next((b for b in all_blocks if b.pk == int(block_filter)), None)

    D0 = Decimal('0')

    # ── Block scope ────────────────────────────────────────────────────────────
    block_qs = Block.objects.filter(residential_complex=rc)
    if selected_block:
        block_qs = block_qs.filter(pk=selected_block.pk)
    block_pks = list(block_qs.values_list('pk', flat=True))

    # ── Apartments ─────────────────────────────────────────────────────────────
    from apps.apartments.models import Apartment
    apt_qs = Apartment.objects.filter(block__in=block_pks)

    apt_total    = apt_qs.count()
    apt_sold     = apt_qs.filter(is_sold=True).count()
    apt_barter   = apt_qs.filter(is_barter=True).count()
    apt_reserved = apt_qs.filter(is_reserved=True, is_sold=False).count()
    apt_free     = apt_qs.filter(is_sold=False, is_reserved=False, is_barter=False).count()

    area_total = apt_qs.aggregate(s=Coalesce(Sum('area'), Value(D0)))['s']
    area_sold  = apt_qs.filter(is_sold=True).aggregate(s=Coalesce(Sum('area'), Value(D0)))['s']
    area_free  = apt_qs.filter(is_sold=False, is_reserved=False, is_barter=False).aggregate(s=Coalesce(Sum('area'), Value(D0)))['s']

    sold_qs = apt_qs.filter(is_sold=True)
    if date_from:
        sold_qs = sold_qs.filter(deal_date__gte=date_from)
    if date_to:
        sold_qs = sold_qs.filter(deal_date__lte=date_to)

    contract_total = sold_qs.aggregate(s=Coalesce(Sum('deal_amount_contract'), Value(D0)))['s']
    paid_total     = sold_qs.aggregate(s=Coalesce(Sum('deal_amount_paid'),     Value(D0)))['s']
    receivables    = sold_qs.aggregate(s=Coalesce(Sum('deal_amount_remaining'), Value(D0)))['s']

    avg_sale_price = (contract_total / area_sold).quantize(Decimal('0.01')) if area_sold > 0 else D0

    # Potential from free apartments — area × average sale price of sold apartments
    free_potential = (area_free * avg_sale_price).quantize(Decimal('0.01')) if avg_sale_price and area_free else D0

    # ── DDS ────────────────────────────────────────────────────────────────────
    sorted_months = []
    try:
        from apps.dds.models import CashFlowRecord, CashAccount

        if selected_block:
            dds_base = CashFlowRecord.objects.filter(block=selected_block)
        else:
            dds_base = CashFlowRecord.objects.filter(
                Q(block__residential_complex=rc) | Q(account__residential_complex=rc)
            ).distinct()

        if date_from:
            dds_base = dds_base.filter(operation_date__gte=date_from)
        if date_to:
            dds_base = dds_base.filter(operation_date__lte=date_to)

        dds_income   = dds_base.filter(direction='in').aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']
        dds_expense  = dds_base.filter(direction='out').aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']
        dds_transfer = dds_base.filter(direction='transfer').aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']

        # ── Поступления от покупателей (БЕЗ возвратов от поставщиков/подрядчиков) ──
        # Возврат от поставщика — это контра-статья к расходам, а не доход покупателей
        supplier_return_q = (
            Q(object_ref__icontains='возврат от поставщ') |
            Q(object_ref__icontains='возврат от подрядч')
        )
        buyer_income     = dds_base.filter(direction='in').exclude(supplier_return_q).aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']
        returns_incoming = dds_base.filter(direction='in').filter(supplier_return_q).aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']

        # ── Возврат покупателю (контра-статья к поступлениям) ──
        # Ловим по типу операции ИЛИ по object_ref (в 1С тип бывает «На расходы»)
        buyer_return_q = (
            Q(operation_type__icontains='возврат') |
            Q(object_ref__icontains='возврат покупател')
        )
        dds_returns  = dds_base.filter(direction='out').filter(buyer_return_q).aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']

        # ── Расходы на объект (БЕЗ возвратов покупателям — те на стороне поступлений) ──
        proj_expense = dds_base.filter(direction='out').exclude(buyer_return_q).aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']

        # ── Итоговые показатели ──
        net_income  = buyer_income   - dds_returns      # поступления нетто
        net_expense = proj_expense   - returns_incoming  # расходы нетто
        wip_balance = net_income     - net_expense       # незавершёнка

        # Cash balance from accounts for this RC
        acc_qs = CashAccount.objects.filter(residential_complex=rc)
        cash_balance = D0
        for acc in acc_qs:
            inc = acc.records.filter(direction='in').aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']
            exp = acc.records.filter(direction='out').aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']
            cash_balance += inc - exp

        # Monthly chart (last 24 months or filtered range)
        monthly_rows = list(
            dds_base.filter(direction__in=['in', 'out'])
            .values('operation_date__year', 'operation_date__month', 'direction')
            .annotate(total=Sum('amount'))
            .order_by('operation_date__year', 'operation_date__month')
        )
        monthly_map = {}
        for row in monthly_rows:
            key = f"{row['operation_date__year']}-{row['operation_date__month']:02d}"
            if key not in monthly_map:
                monthly_map[key] = {'in': 0.0, 'out': 0.0}
            monthly_map[key][row['direction']] += float(row['total'])
        sorted_months = sorted(monthly_map)[-24:]
        chart_months_json  = json.dumps(sorted_months)
        chart_income_json  = json.dumps([round(monthly_map[m]['in'],  2) for m in sorted_months])
        chart_expense_json = json.dumps([round(monthly_map[m]['out'], 2) for m in sorted_months])

    except Exception:
        dds_income = dds_expense = dds_transfer = dds_returns = cash_balance = D0
        buyer_income = proj_expense = returns_incoming = D0
        net_income = net_expense = wip_balance = D0
        chart_months_json = chart_income_json = chart_expense_json = json.dumps([])

    # ── Estimate & actual expenses ─────────────────────────────────────────────
    try:
        from apps.estimates.models import EstimateItem, ExtraBlockExpense

        estimate_plan = EstimateItem.objects.filter(
            section__estimate__block__in=block_pks
        ).aggregate(s=Coalesce(Sum('total_amount'), Value(D0)))['s']

        pf_qs = FloorExpense.objects.filter(floor__stage__block__in=block_pks)
        if date_from:
            pf_qs = pf_qs.filter(expense_date__gte=date_from)
        if date_to:
            pf_qs = pf_qs.filter(expense_date__lte=date_to)
        pf_actual = pf_qs.aggregate(s=Coalesce(Sum('total_amount'), Value(D0)))['s']

        extra_qs = ExtraBlockExpense.objects.filter(block__in=block_pks)
        if date_from:
            extra_qs = extra_qs.filter(date__gte=date_from)
        if date_to:
            extra_qs = extra_qs.filter(date__lte=date_to)
        extra_total = extra_qs.aggregate(s=Coalesce(Sum('amount'), Value(D0)))['s']

    except Exception:
        estimate_plan = pf_actual = extra_total = D0

    pf_remaining   = max(D0, estimate_plan - pf_actual)
    total_spend    = pf_actual + extra_total
    future_budget  = max(D0, estimate_plan - net_expense)

    # Фактическая себестоимость — только потраченное
    cost_per_m2_actual = (total_spend / area_total).quantize(Decimal('0.01')) if area_total > 0 else D0

    # Прогнозная себестоимость — смета целиком + внесметные (будущие расходы учтены)
    projected_total    = estimate_plan + extra_total
    cost_per_m2        = (projected_total / area_total).quantize(Decimal('0.01')) if area_total > 0 else D0

    # Маржа м² прогнозная (цена продажи vs полная себестоимость)
    margin_per_m2      = avg_sale_price - cost_per_m2 if (avg_sale_price and cost_per_m2) else D0

    # ── Margin ─────────────────────────────────────────────────────────────────
    margin_cash     = dds_income - dds_expense
    margin_contract = contract_total - estimate_plan
    margin_actual   = paid_total - total_spend

    # ── Pie chart ──────────────────────────────────────────────────────────────
    pie_labels_json = json.dumps(['Продано', 'Свободно', 'Бронь', 'Бартер'])
    pie_data_json   = json.dumps([apt_sold, apt_free, apt_reserved, apt_barter])

    # ── Budget progress ────────────────────────────────────────────────────────
    budget_pct = int(min(100, (pf_actual / estimate_plan * 100))) if estimate_plan > 0 else 0
    sales_pct  = int(min(100, (apt_sold / apt_total * 100))) if apt_total > 0 else 0
    paid_pct   = int(min(100, (paid_total / contract_total * 100))) if contract_total > 0 else 0

    return render(request, 'analytics/rc_detail.html', {
        'rc': rc,
        'all_rcs': all_rcs,
        'all_blocks': all_blocks,
        'selected_block': selected_block,
        'block_filter': block_filter,
        'date_from': date_from,
        'date_to': date_to,
        'is_filtered': bool(date_from or date_to or selected_block),
        # Apartments
        'apt_total': apt_total, 'apt_sold': apt_sold, 'apt_free': apt_free,
        'apt_reserved': apt_reserved, 'apt_barter': apt_barter,
        'area_total': area_total, 'area_sold': area_sold, 'area_free': area_free,
        'contract_total': contract_total, 'paid_total': paid_total,
        'receivables': receivables, 'avg_sale_price': avg_sale_price,
        'free_potential': free_potential,
        'sales_pct': sales_pct, 'paid_pct': paid_pct,
        # DDS
        'dds_income': dds_income, 'dds_expense': dds_expense,
        'dds_transfer': dds_transfer, 'dds_returns': dds_returns,
        'buyer_income': buyer_income, 'proj_expense': proj_expense,
        'returns_incoming': returns_incoming,
        'net_income': net_income, 'net_expense': net_expense, 'wip_balance': wip_balance,
        'cash_balance': cash_balance,
        # Estimates
        'estimate_plan': estimate_plan, 'pf_actual': pf_actual,
        'pf_remaining': pf_remaining, 'extra_total': extra_total,
        'total_spend': total_spend,
        'projected_total': projected_total,
        'cost_per_m2_actual': cost_per_m2_actual,
        'cost_per_m2': cost_per_m2,
        'margin_per_m2': margin_per_m2,
        'future_budget': future_budget,
        'budget_pct': budget_pct,
        # Margin
        'margin_cash': margin_cash, 'margin_contract': margin_contract,
        'margin_actual': margin_actual,
        # Charts
        'chart_months_json': chart_months_json,
        'chart_income_json': chart_income_json,
        'chart_expense_json': chart_expense_json,
        'pie_labels_json': pie_labels_json,
        'pie_data_json': pie_data_json,
        'has_chart_data': bool(sorted_months),
    })
