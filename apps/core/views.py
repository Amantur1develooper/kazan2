import json
from decimal import Decimal
from django.shortcuts import render
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value

from apps.projects.models import Organization, ResidentialComplex, Stage, FloorExpense


def dashboard(request):
    # Global financials
    all_floor_actual = FloorExpense.objects.aggregate(
        total=Coalesce(Sum('total_amount'), Value(Decimal('0')))
    )['total']
    manual_stage_actual = Stage.objects.filter(floors__isnull=True).aggregate(
        total=Coalesce(Sum('actual_expenses'), Value(Decimal('0')))
    )['total']
    total_actual = all_floor_actual + manual_stage_actual

    total_planned = Stage.objects.aggregate(
        total=Coalesce(Sum('planned_expenses'), Value(Decimal('0')))
    )['total']
    total_deviation = total_actual - total_planned

    # Per-organization
    orgs = Organization.objects.prefetch_related('complexes').all()
    org_stats = []
    for org in orgs:
        planned = org.total_planned_expenses
        actual = org.total_actual_expenses
        org_stats.append({'org': org, 'planned': planned, 'actual': actual,
                           'deviation': actual - planned})

    # Per-complex
    complexes = ResidentialComplex.objects.select_related('organization').prefetch_related('blocks__stages').all()
    complex_stats = []
    for c in complexes:
        planned = c.total_planned_expenses
        actual = c.total_actual_expenses
        complex_stats.append({'complex': c, 'planned': planned, 'actual': actual,
                               'deviation': actual - planned, 'profit': c.total_planned_cost - actual})

    context = {
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_deviation': total_deviation,
        'org_stats': org_stats,
        'complex_stats': complex_stats,
        'complexes_count': complexes.count(),
        'chart_labels': json.dumps([s['complex'].name for s in complex_stats]),
        'chart_planned': json.dumps([float(s['planned']) for s in complex_stats]),
        'chart_actual': json.dumps([float(s['actual']) for s in complex_stats]),
    }
    return render(request, 'dashboard/index.html', context)
