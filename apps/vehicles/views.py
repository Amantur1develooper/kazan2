from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.db.models import Value

from apps.projects.models import Organization, Block, ResidentialComplex
from .models import VehicleTransaction
from .parser import parse_vehicles_excel


# ── Helpers ───────────────────────────────────────────────────────────────────

def _block_map(blocks):
    """Build fuzzy name→block lookup for import matching."""
    mapping = {}
    for b in blocks:
        # full name
        mapping[b.residential_complex.name.lower()] = b
        # short block name variants
        for alias in [
            f'блок {b.name}'.lower(),
            f'блок-{b.name}'.lower(),
            b.name.lower(),
        ]:
            mapping[alias] = b
    return mapping


def _match_block(text, bmap):
    if not text:
        return None
    t = text.lower().strip()
    if t in bmap:
        return bmap[t]
    for key, blk in bmap.items():
        if key in t or t in key:
            return blk
    return None


# ── List / overview ───────────────────────────────────────────────────────────

def vehicle_list(request):
    org_id   = request.GET.get('org')
    block_id = request.GET.get('block')
    status   = request.GET.get('status', '')
    q        = request.GET.get('q', '').strip()

    qs = VehicleTransaction.objects.select_related(
        'organization', 'source_block__residential_complex',
        'target_block__residential_complex'
    )
    if org_id:
        qs = qs.filter(organization_id=org_id)
    if block_id:
        qs = qs.filter(Q(source_block_id=block_id) | Q(target_block_id=block_id))
    if status == 'available':
        qs = qs.filter(is_sold=False)
    elif status == 'sold':
        qs = qs.filter(is_sold=True)
    if q:
        qs = qs.filter(
            Q(vehicle_name__icontains=q) |
            Q(counterparty__icontains=q) |
            Q(purpose__icontains=q) |
            Q(source_text__icontains=q)
        )

    transactions = list(qs.order_by('-date', '-created_at'))

    # Totals
    total_in   = sum(t.amount_in  for t in transactions)
    total_out  = sum(t.amount_out for t in transactions)
    total_loss = sum(t.loss       for t in transactions)
    in_balance  = [t for t in transactions if not t.is_sold]

    orgs   = Organization.objects.order_by('name')
    blocks = Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    )

    context = {
        'transactions':   transactions,
        'total_in':       total_in,
        'total_out':      total_out,
        'total_loss':     total_loss,
        'in_balance':     in_balance,
        'orgs':           orgs,
        'blocks':         blocks,
        'filter_org':     org_id,
        'filter_block':   block_id,
        'filter_status':  status,
        'filter_q':       q,
    }
    return render(request, 'vehicles/vehicle_list.html', context)


# ── Import ────────────────────────────────────────────────────────────────────

def vehicle_import(request):
    orgs   = list(Organization.objects.order_by('name'))
    blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))

    if request.method == 'POST':
        org_id = request.POST.get('organization')
        f = request.FILES.get('file')
        if not f or not org_id:
            messages.error(request, 'Выберите компанию и загрузите файл.')
            return render(request, 'vehicles/vehicle_import.html', {'orgs': orgs, 'blocks': blocks})

        try:
            import tempfile, os
            suffix = os.path.splitext(f.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in f.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            rows = parse_vehicles_excel(tmp_path)
            os.unlink(tmp_path)

            org = Organization.objects.get(pk=org_id)
            bmap = _block_map(blocks)

            to_create = []
            for row in rows:
                to_create.append(VehicleTransaction(
                    organization=org,
                    date=row['date'],
                    vehicle_name=row['vehicle_name'],
                    source_block=_match_block(row['source_text'], bmap),
                    source_text=row['source_text'],
                    amount_in=row['amount_in'],
                    amount_out=row['amount_out'],
                    counterparty=row['counterparty'],
                    target_block=_match_block(row['target_text'], bmap),
                    target_text=row['target_text'],
                    purpose=row['purpose'],
                    source_file=f.name,
                ))

            VehicleTransaction.objects.bulk_create(to_create)
            messages.success(request, f'Импортировано {len(to_create)} операций из «{f.name}».')
            return redirect('vehicle_list')

        except Exception as e:
            messages.error(request, f'Ошибка чтения файла: {e}')

    return render(request, 'vehicles/vehicle_import.html', {'orgs': orgs, 'blocks': blocks})


# ── Create / Edit / Delete ────────────────────────────────────────────────────

def vehicle_create(request):
    orgs   = list(Organization.objects.order_by('name'))
    blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))
    if request.method == 'POST':
        try:
            p = request.POST
            VehicleTransaction.objects.create(
                organization_id = p.get('organization') or None,
                date            = p['date'],
                vehicle_name    = p['vehicle_name'].strip(),
                source_block_id = p.get('source_block') or None,
                source_text     = p.get('source_text', '').strip(),
                amount_in       = Decimal(p.get('amount_in', '0') or '0'),
                amount_out      = Decimal(p.get('amount_out', '0') or '0'),
                counterparty    = p.get('counterparty', '').strip(),
                target_block_id = p.get('target_block') or None,
                target_text     = p.get('target_text', '').strip(),
                purpose         = p.get('purpose', '').strip(),
                is_sold         = 'is_sold' in p,
                notes           = p.get('notes', '').strip(),
            )
            messages.success(request, 'Операция добавлена.')
            return redirect('vehicle_list')
        except Exception as e:
            messages.error(request, f'Ошибка: {e}')
    return render(request, 'vehicles/vehicle_form.html', {
        'orgs': orgs, 'blocks': blocks, 'title': 'Добавить операцию',
    })


def vehicle_edit(request, pk):
    obj    = get_object_or_404(VehicleTransaction, pk=pk)
    orgs   = list(Organization.objects.order_by('name'))
    blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))
    if request.method == 'POST':
        try:
            p = request.POST
            obj.organization_id = p.get('organization') or None
            obj.date            = p['date']
            obj.vehicle_name    = p['vehicle_name'].strip()
            obj.source_block_id = p.get('source_block') or None
            obj.source_text     = p.get('source_text', '').strip()
            obj.amount_in       = Decimal(p.get('amount_in', '0') or '0')
            obj.amount_out      = Decimal(p.get('amount_out', '0') or '0')
            obj.counterparty    = p.get('counterparty', '').strip()
            obj.target_block_id = p.get('target_block') or None
            obj.target_text     = p.get('target_text', '').strip()
            obj.purpose         = p.get('purpose', '').strip()
            obj.is_sold         = 'is_sold' in p
            obj.notes           = p.get('notes', '').strip()
            obj.save()
            messages.success(request, 'Операция обновлена.')
            return redirect('vehicle_list')
        except Exception as e:
            messages.error(request, f'Ошибка: {e}')
    return render(request, 'vehicles/vehicle_form.html', {
        'orgs': orgs, 'blocks': blocks, 'obj': obj, 'title': 'Редактировать операцию',
    })


def vehicle_toggle_sold(request, pk):
    obj = get_object_or_404(VehicleTransaction, pk=pk)
    if request.method == 'POST':
        obj.is_sold = not obj.is_sold
        obj.save(update_fields=['is_sold'])
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'vehicle_list'
    return redirect(next_url)


def vehicle_delete(request, pk):
    obj = get_object_or_404(VehicleTransaction, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Операция удалена.')
        return redirect('vehicle_list')
    return render(request, 'vehicles/vehicle_confirm_delete.html', {'obj': obj})
