import json
import tempfile
import os
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.db.models import Value

from apps.projects.models import Organization, Block, ResidentialComplex
from .models import Apartment
from .parser import parse_apartments_excel

ZERO = Decimal('0')


# ── List ─────────────────────────────────────────────────────────────────────

def apartment_list(request):
    org_id   = request.GET.get('org', '')
    rc_id    = request.GET.get('rc', '')
    block_id = request.GET.get('block', '')
    status   = request.GET.get('status', '')
    rooms    = request.GET.get('rooms', '')
    q        = request.GET.get('q', '').strip()

    qs = Apartment.objects.select_related(
        'block__residential_complex__organization'
    )
    if org_id:
        qs = qs.filter(block__residential_complex__organization_id=org_id)
    if rc_id:
        qs = qs.filter(block__residential_complex_id=rc_id)
    if block_id:
        qs = qs.filter(block_id=block_id)
    if rooms:
        qs = qs.filter(rooms=rooms)
    if status == 'free':
        qs = qs.filter(is_sold=False, is_reserved=False, is_barter=False)
    elif status == 'reserved':
        qs = qs.filter(is_reserved=True, is_sold=False)
    elif status == 'sold':
        qs = qs.filter(is_sold=True, is_barter=False)
    elif status == 'barter':
        qs = qs.filter(is_barter=True)
    if q:
        qs = qs.filter(
            Q(apartment_number__icontains=q) |
            Q(client_name__icontains=q) |
            Q(phone__icontains=q)
        )

    apartments = list(qs.order_by(
        'block__residential_complex__name', 'block__name', 'floor', 'apartment_number'
    ))

    # Stats
    total_count    = len(apartments)
    free_count     = sum(1 for a in apartments if a.status == Apartment.STATUS_FREE)
    reserved_count = sum(1 for a in apartments if a.status == Apartment.STATUS_RESERVED)
    sold_count     = sum(1 for a in apartments if a.status == Apartment.STATUS_SOLD)
    barter_count   = sum(1 for a in apartments if a.status == Apartment.STATUS_BARTER)

    total_area     = sum(a.area              for a in apartments)
    sold_area      = sum(a.area              for a in apartments if a.is_sold)
    free_area      = sum(a.area              for a in apartments if a.status == Apartment.STATUS_FREE)
    total_paid     = sum(a.deal_amount_paid  for a in apartments)
    total_contract = sum(a.deal_amount_contract for a in apartments if a.is_sold)
    total_remaining= sum(a.deal_amount_remaining for a in apartments if a.is_sold)

    orgs   = Organization.objects.order_by('name')
    rcs    = ResidentialComplex.objects.select_related('organization').order_by('name')
    blocks = Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    )

    # Floor plan grid — only when a single block is selected
    floors_grid = None
    block_obj   = None
    if block_id:
        # Use all apartments of the block (unfiltered by status/rooms/q) for the grid
        all_block_apts = list(
            Apartment.objects.filter(block_id=block_id)
            .order_by('floor', 'apartment_number')
        )
        if all_block_apts:
            try:
                block_obj = Block.objects.select_related('residential_complex').get(pk=block_id)
            except Block.DoesNotExist:
                pass
            floor_nums = sorted(set(a.floor for a in all_block_apts), reverse=True)
            floors_grid = [
                (f, [a for a in all_block_apts if a.floor == f])
                for f in floor_nums
            ]

    context = {
        'apartments':     apartments,
        'total_count':    total_count,
        'free_count':     free_count,
        'reserved_count': reserved_count,
        'sold_count':     sold_count,
        'barter_count':   barter_count,
        'total_area':     total_area,
        'sold_area':      sold_area,
        'free_area':      free_area,
        'total_paid':     total_paid,
        'total_contract': total_contract,
        'total_remaining':total_remaining,
        'orgs':       orgs,
        'rcs':        rcs,
        'blocks':     blocks,
        'block_obj':  block_obj,
        'floors_grid':floors_grid,
        'filter_org':    org_id,
        'filter_rc':     rc_id,
        'filter_block':  block_id,
        'filter_status': status,
        'filter_rooms':  rooms,
        'filter_q':      q,
    }
    return render(request, 'apartments/apartment_list.html', context)


# ── Detail ────────────────────────────────────────────────────────────────────

def apartment_detail(request, pk):
    apt = get_object_or_404(
        Apartment.objects.select_related(
            'block__residential_complex__organization'
        ), pk=pk
    )
    return render(request, 'apartments/apartment_detail.html', {'apt': apt})


# ── Import ────────────────────────────────────────────────────────────────────

def apartment_import(request):
    orgs   = list(Organization.objects.order_by('name'))
    blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))
    blocks_by_rc = {}
    for b in blocks:
        blocks_by_rc.setdefault(str(b.residential_complex_id), []).append(
            {'id': b.pk, 'name': f'Блок {b.name}'}
        )
    blocks_by_rc_json = json.dumps(blocks_by_rc)

    rcs = list(ResidentialComplex.objects.select_related('organization').order_by('name'))

    if request.method == 'POST':
        block_id = request.POST.get('block')
        update_existing = request.POST.get('update_existing') == 'on'
        create_missing  = request.POST.get('create_missing')  == 'on'
        f = request.FILES.get('file')

        if not f or not block_id:
            messages.error(request, 'Выберите блок и загрузите файл.')
            return render(request, 'apartments/apartment_import.html', {
                'orgs': orgs, 'rcs': rcs, 'blocks': blocks,
                'blocks_by_rc_json': blocks_by_rc_json,
            })

        block = get_object_or_404(Block, pk=block_id)

        suffix = os.path.splitext(f.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in f.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            rows = parse_apartments_excel(tmp_path)
        except Exception as e:
            os.unlink(tmp_path)
            messages.error(request, f'Ошибка чтения файла: {e}')
            return render(request, 'apartments/apartment_import.html', {
                'orgs': orgs, 'rcs': rcs, 'blocks': blocks,
                'blocks_by_rc_json': blocks_by_rc_json,
            })
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        existing = {a.apartment_number: a for a in Apartment.objects.filter(block=block)}

        created = updated = skipped = returns = resales = barters = 0

        for row in rows:
            apt_num = row['apartment_number']
            row['block'] = block
            row['source_file'] = f.name

            if apt_num in existing:
                if not update_existing:
                    skipped += 1
                    continue
                apt = existing[apt_num]
                old_sold = apt.is_sold
                old_name = (apt.client_name or '').strip().lower()
                new_name = (row['client_name'] or '').strip().lower()

                # Detect RETURN
                if old_sold and not row['client_name'] and row['deal_amount_paid'] == 0 and not row['is_reserved']:
                    row['is_sold'] = False
                    row['is_reserved'] = False
                    row['client_name'] = ''
                    returns += 1
                # Detect RESALE
                elif old_name and new_name and old_name != new_name:
                    resales += 1

                if row.get('is_barter'):
                    barters += 1

                for k, v in row.items():
                    if k != 'block':
                        setattr(apt, k, v)
                apt.save()
                updated += 1
            else:
                if not create_missing:
                    skipped += 1
                    continue
                if row.get('is_barter'):
                    barters += 1
                Apartment.objects.create(**row)
                created += 1

        parts = [f'Создано: {created}', f'обновлено: {updated}']
        if skipped:
            parts.append(f'пропущено: {skipped}')
        if returns:
            parts.append(f'возвратов: {returns}')
        if resales:
            parts.append(f'перепродаж: {resales}')
        if barters:
            parts.append(f'бартеров: {barters}')

        messages.success(request, f'Импорт завершён — {", ".join(parts)}.')
        return redirect('apartment_list')

    return render(request, 'apartments/apartment_import.html', {
        'orgs': orgs, 'rcs': rcs, 'blocks': blocks,
        'blocks_by_rc_json': blocks_by_rc_json,
    })


# ── Create / Edit / Delete ────────────────────────────────────────────────────

def apartment_create(request):
    blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))
    if request.method == 'POST':
        try:
            p = request.POST
            Apartment.objects.create(
                block_id            = p['block'],
                floor               = int(p.get('floor', 1) or 1),
                apartment_number    = p['apartment_number'].strip(),
                rooms               = int(p.get('rooms', 1) or 1),
                area                = Decimal(p['area']),
                planned_price_per_m2= Decimal(p.get('planned_price_per_m2', '0') or '0'),
                fact_price_per_m2   = Decimal(p.get('fact_price_per_m2', '0') or '0'),
                client_name         = p.get('client_name', '').strip(),
                phone               = p.get('phone', '').strip(),
                deal_date           = p.get('deal_date') or None,
                deal_number         = p.get('deal_number', '').strip(),
                deal_amount_contract= Decimal(p.get('deal_amount_contract', '0') or '0'),
                deal_amount_paid    = Decimal(p.get('deal_amount_paid', '0') or '0'),
                deal_amount_remaining=Decimal(p.get('deal_amount_remaining','0') or '0'),
                discount            = Decimal(p.get('discount', '0') or '0'),
                is_sold             = 'is_sold'     in p,
                is_reserved         = 'is_reserved' in p,
                is_barter           = 'is_barter'   in p,
                contract_type       = p.get('contract_type', '').strip(),
                curator             = p.get('curator', '').strip(),
                notes               = p.get('notes', '').strip(),
            )
            messages.success(request, 'Квартира добавлена.')
            return redirect('apartment_list')
        except Exception as e:
            messages.error(request, f'Ошибка: {e}')
    return render(request, 'apartments/apartment_form.html', {
        'blocks': blocks, 'title': 'Добавить квартиру',
    })


def apartment_edit(request, pk):
    apt    = get_object_or_404(Apartment, pk=pk)
    blocks = list(Block.objects.select_related('residential_complex').order_by(
        'residential_complex__name', 'name'
    ))
    if request.method == 'POST':
        try:
            p = request.POST
            apt.block_id             = p['block']
            apt.floor                = int(p.get('floor', 1) or 1)
            apt.apartment_number     = p['apartment_number'].strip()
            apt.rooms                = int(p.get('rooms', 1) or 1)
            apt.area                 = Decimal(p['area'])
            apt.planned_price_per_m2 = Decimal(p.get('planned_price_per_m2','0') or '0')
            apt.fact_price_per_m2    = Decimal(p.get('fact_price_per_m2','0') or '0')
            apt.client_name          = p.get('client_name','').strip()
            apt.phone                = p.get('phone','').strip()
            apt.deal_date            = p.get('deal_date') or None
            apt.deal_number          = p.get('deal_number','').strip()
            apt.deal_amount_contract = Decimal(p.get('deal_amount_contract','0') or '0')
            apt.deal_amount_paid     = Decimal(p.get('deal_amount_paid','0') or '0')
            apt.deal_amount_remaining= Decimal(p.get('deal_amount_remaining','0') or '0')
            apt.discount             = Decimal(p.get('discount','0') or '0')
            apt.is_sold              = 'is_sold'     in p
            apt.is_reserved          = 'is_reserved' in p
            apt.is_barter            = 'is_barter'   in p
            apt.contract_type        = p.get('contract_type','').strip()
            apt.curator              = p.get('curator','').strip()
            apt.notes                = p.get('notes','').strip()
            apt.save()
            messages.success(request, 'Квартира обновлена.')
            return redirect('apartment_detail', pk=apt.pk)
        except Exception as e:
            messages.error(request, f'Ошибка: {e}')
    return render(request, 'apartments/apartment_form.html', {
        'blocks': blocks, 'obj': apt, 'title': 'Редактировать квартиру',
    })


def apartment_delete(request, pk):
    apt = get_object_or_404(Apartment, pk=pk)
    if request.method == 'POST':
        apt.delete()
        messages.success(request, 'Квартира удалена.')
        return redirect('apartment_list')
    return render(request, 'apartments/apartment_confirm_delete.html', {'apt': apt})
