import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value

from .decorators import editor_required
from .models import MainCash, CashTransaction
from .forms import CashTransactionForm
from apps.projects.models import Organization, ResidentialComplex, Stage, FloorExpense


def dashboard(request):
    cash = MainCash.objects.first()

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

    cash_balance = cash.current_balance if cash else Decimal('0')
    net_balance = cash_balance - total_actual

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
        'cash': cash,
        'cash_balance': cash_balance,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'total_deviation': total_deviation,
        'net_balance': net_balance,
        'org_stats': org_stats,
        'complex_stats': complex_stats,
        'complexes_count': complexes.count(),
        'chart_labels': json.dumps([s['complex'].name for s in complex_stats]),
        'chart_planned': json.dumps([float(s['planned']) for s in complex_stats]),
        'chart_actual': json.dumps([float(s['actual']) for s in complex_stats]),
    }
    return render(request, 'dashboard/index.html', context)


def cash_detail(request):
    cash = MainCash.objects.first()
    if not cash:
        cash = MainCash.objects.create(name='Главная касса')
    transactions = cash.transactions.order_by('-date', '-created_at')
    context = {'cash': cash, 'transactions': transactions}
    return render(request, 'core/cash_detail.html', context)


@editor_required
def transaction_create(request):
    cash = MainCash.objects.first()
    if not cash:
        cash = MainCash.objects.create(name='Главная касса')
    if request.method == 'POST':
        form = CashTransactionForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.main_cash = cash
            t.save()
            messages.success(request, 'Транзакция добавлена.')
            return redirect('cash_detail')
    else:
        form = CashTransactionForm()
    return render(request, 'core/transaction_form.html', {'form': form, 'cash': cash})


@editor_required
def transaction_delete(request, pk):
    transaction = get_object_or_404(CashTransaction, pk=pk)
    if request.method == 'POST':
        transaction.delete()
        messages.success(request, 'Транзакция удалена.')
        return redirect('cash_detail')
    return render(request, 'core/transaction_confirm_delete.html', {'transaction': transaction})
