import json
from decimal import Decimal
from django.shortcuts import render
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.db.models import Value
from django.contrib.auth.views import LoginView

from apps.projects.models import Organization, ResidentialComplex, Stage, FloorExpense, Block


class SmartLoginView(LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        user = self.request.user
        is_admin = user.is_staff or user.groups.filter(name='Производство').exists()
        if not is_admin:
            from apps.planfact.models import BlockAccess
            if BlockAccess.objects.filter(user=user).exists():
                return '/planfact/'
        return super().get_success_url()


def dashboard(request):
    from apps.dds.models import CashFlowRecord, CashAccount
    from apps.estimates.models import ExtraBlockExpense
    from apps.vehicles.models import VehicleTransaction

    ZERO = Decimal('0')

    # ── П/Ф (материальный счётчик) ──────────────────────────────────────────
    pf_all_floors = FloorExpense.objects.aggregate(
        total=Coalesce(Sum('total_amount'), Value(ZERO))
    )['total']
    pf_manual = Stage.objects.filter(floors__isnull=True).aggregate(
        total=Coalesce(Sum('actual_expenses'), Value(ZERO))
    )['total']
    total_pf = pf_all_floors + pf_manual

    total_smeta = Stage.objects.aggregate(
        total=Coalesce(Sum('planned_expenses'), Value(ZERO))
    )['total']

    # ── ДДС (денежный счётчик) ──────────────────────────────────────────────
    total_dds_income = CashFlowRecord.objects.filter(
        direction='in'
    ).aggregate(s=Coalesce(Sum('amount'), Value(ZERO)))['s']

    total_dds_expense = CashFlowRecord.objects.filter(
        direction='out'
    ).aggregate(s=Coalesce(Sum('amount'), Value(ZERO)))['s']

    # ── Внесметные расходы ──────────────────────────────────────────────────
    total_extra = ExtraBlockExpense.objects.aggregate(
        s=Coalesce(Sum('amount'), Value(ZERO))
    )['s']

    # ── Касса ────────────────────────────────────────────────────────────────
    cash_balance = total_dds_income - total_dds_expense

    # ── Δ-долг ──────────────────────────────────────────────────────────────
    # >0 переплатили (подрядчик нам должен), <0 мы должны
    total_debt = total_dds_expense - total_pf

    # ── Маржа ────────────────────────────────────────────────────────────────
    total_planned_revenue = ResidentialComplex.objects.aggregate(
        s=Coalesce(Sum('total_planned_cost'), Value(ZERO))
    )['s']
    total_margin = total_planned_revenue - total_pf - total_extra

    # ── Склад авто ──────────────────────────────────────────────────────────
    veh_in   = sum(t.amount_in  for t in VehicleTransaction.objects.all() if t.amount_in  > 0)
    veh_out  = sum(abs(t.amount_out) for t in VehicleTransaction.objects.all() if t.amount_out < 0)
    veh_loss = veh_in - veh_out

    # ── Данные по ЖК ────────────────────────────────────────────────────────
    complexes = list(
        ResidentialComplex.objects.select_related('organization')
        .prefetch_related('blocks__stages')
        .all()
    )
    rc_ids = [c.pk for c in complexes]

    # DDS per RC
    dds_income_by_rc = {
        r['block__residential_complex_id']: r['s']
        for r in CashFlowRecord.objects.filter(
            block__residential_complex_id__in=rc_ids, direction='in'
        ).values('block__residential_complex_id').annotate(s=Sum('amount'))
    }
    dds_expense_by_rc = {
        r['block__residential_complex_id']: r['s']
        for r in CashFlowRecord.objects.filter(
            block__residential_complex_id__in=rc_ids, direction='out'
        ).values('block__residential_complex_id').annotate(s=Sum('amount'))
    }

    # Extra expenses per RC (via block)
    extra_by_rc = {}
    for e in ExtraBlockExpense.objects.select_related('block__residential_complex').all():
        rc_id = e.block.residential_complex_id
        extra_by_rc[rc_id] = extra_by_rc.get(rc_id, ZERO) + e.amount

    complex_stats = []
    for c in complexes:
        pf_actual  = c.total_actual_expenses
        smeta_plan = c.total_planned_expenses
        dds_in     = dds_income_by_rc.get(c.pk, ZERO)
        dds_out    = dds_expense_by_rc.get(c.pk, ZERO)
        extra      = extra_by_rc.get(c.pk, ZERO)
        total_cost = pf_actual + extra

        debt   = dds_out - pf_actual
        margin = c.total_planned_cost - total_cost

        sqm = c.square_meters
        pf_per_sqm  = (pf_actual / sqm).quantize(Decimal('1')) if sqm and pf_actual else None
        dds_per_sqm = (dds_out   / sqm).quantize(Decimal('1')) if sqm and dds_out   else None

        complex_stats.append({
            'complex':     c,
            'smeta':       smeta_plan,
            'pf_actual':   pf_actual,
            'dds_income':  dds_in,
            'dds_expense': dds_out,
            'extra':       extra,
            'total_cost':  total_cost,
            'debt':        debt,
            'margin':      margin,
            'pf_per_sqm':  pf_per_sqm,
            'dds_per_sqm': dds_per_sqm,
        })

    # ── Данные по организациям ───────────────────────────────────────────────
    orgs = list(Organization.objects.prefetch_related('complexes').all())
    org_stats = []
    for org in orgs:
        rc_for_org = [c for c in complexes if c.organization_id == org.pk]
        rc_ids_org = [c.pk for c in rc_for_org]

        pf   = sum(s['pf_actual']   for s in complex_stats if s['complex'].pk in rc_ids_org)
        dds  = sum(s['dds_expense'] for s in complex_stats if s['complex'].pk in rc_ids_org)
        smeta = sum(s['smeta']      for s in complex_stats if s['complex'].pk in rc_ids_org)
        margin = sum(s['margin']    for s in complex_stats if s['complex'].pk in rc_ids_org)
        debt  = dds - pf

        org_stats.append({
            'org':    org,
            'smeta':  smeta,
            'pf':     pf,
            'dds':    dds,
            'debt':   debt,
            'margin': margin,
        })

    # ── Графики ──────────────────────────────────────────────────────────────
    chart_labels   = json.dumps([s['complex'].name for s in complex_stats])
    chart_smeta    = json.dumps([float(s['smeta'])       for s in complex_stats])
    chart_pf       = json.dumps([float(s['pf_actual'])   for s in complex_stats])
    chart_dds      = json.dumps([float(s['dds_expense']) for s in complex_stats])

    context = {
        # Global counters
        'total_smeta':          total_smeta,
        'total_pf':             total_pf,
        'total_dds_income':     total_dds_income,
        'total_dds_expense':    total_dds_expense,
        'total_extra':          total_extra,
        'cash_balance':         cash_balance,
        'total_debt':           total_debt,
        'total_planned_revenue':total_planned_revenue,
        'total_margin':         total_margin,
        # Vehicles
        'veh_in':   veh_in,
        'veh_out':  veh_out,
        'veh_loss': veh_loss,
        # Tables
        'org_stats':     org_stats,
        'complex_stats': complex_stats,
        'complexes_count': len(complexes),
        # Charts
        'chart_labels': chart_labels,
        'chart_smeta':  chart_smeta,
        'chart_pf':     chart_pf,
        'chart_dds':    chart_dds,
    }
    return render(request, 'dashboard/index.html', context)
