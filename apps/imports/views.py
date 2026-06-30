import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from apps.core.decorators import editor_required
from .models import ExcelImport, ImportLog
from .forms import ExcelImportForm, FloorSelectForm
from .floor_parser import parse_floor_excel, apply_floor_import
from apps.projects.models import Floor, Stage


def import_list(request):
    imports = ExcelImport.objects.select_related('target_floor__stage__block__residential_complex').all()
    return render(request, 'imports/import_list.html', {'imports': imports})


@editor_required
def import_upload(request):
    """
    Two-step upload:
      GET  → show floor selection form
      POST (step1) → validate floor selection, show file upload
      POST (step2) → upload file + process
    """
    step = request.POST.get('step', '1')

    # ── Step 1: Select floor ──────────────────────────────────────────────────
    if request.method == 'POST' and step == '1':
        floor_form = FloorSelectForm(request.POST)
        if floor_form.is_valid():
            cd = floor_form.cleaned_data
            stage = cd['stage']
            floor = cd.get('floor')
            new_num = cd.get('new_floor_number')

            if not floor and new_num:
                floor = Floor.objects.create(
                    stage=stage,
                    number=new_num,
                    name='',
                )

            # Store floor pk in session, show file upload step
            request.session['import_floor_pk'] = floor.pk
            file_form = ExcelImportForm()
            return render(request, 'imports/import_upload.html', {
                'step': '2',
                'floor': floor,
                'file_form': file_form,
            })

    # ── Step 2: Upload file ───────────────────────────────────────────────────
    elif request.method == 'POST' and step == '2':
        floor_pk = request.session.get('import_floor_pk')
        floor = get_object_or_404(Floor, pk=floor_pk) if floor_pk else None

        if not floor:
            messages.error(request, 'Сессия истекла. Начните заново.')
            return redirect('import_upload')

        file_form = ExcelImportForm(request.POST, request.FILES)
        if file_form.is_valid():
            excel_import = file_form.save(commit=False)
            excel_import.original_filename = request.FILES['file'].name
            excel_import.target_floor = floor
            excel_import.save()

            try:
                parsed = parse_floor_excel(excel_import.file.path)
                request.session['import_parsed_items'] = len(parsed.get('items', []))
                request.session['import_doc_title'] = parsed.get('doc_title', '')
                request.session['import_format'] = parsed.get('format', 'generic')

                # Store preview (first 20 items)
                preview_items = parsed.get('items', [])[:20]
                for item in preview_items:
                    item['quantity'] = float(item['quantity'])
                    item['unit_price'] = float(item['unit_price'])
                    item['total_amount'] = float(item['total_amount'])
                request.session['import_preview_items'] = preview_items

                request.session['import_id'] = excel_import.pk
                return redirect('import_preview', pk=excel_import.pk)

            except Exception as e:
                excel_import.status = 'error'
                excel_import.error_message = str(e)
                excel_import.save()
                messages.error(request, f'Ошибка чтения файла: {e}')
                return redirect('import_list')

        return render(request, 'imports/import_upload.html', {
            'step': '2',
            'floor': floor,
            'file_form': file_form,
        })

    # ── GET: Show floor selection (or skip to step 2 if ?floor=pk given) ────────
    floor_pk_param = request.GET.get('floor')
    if floor_pk_param:
        floor = get_object_or_404(
            Floor.objects.select_related('stage__block__residential_complex__organization'),
            pk=floor_pk_param,
        )
        request.session['import_floor_pk'] = floor.pk
        from django.urls import reverse
        return render(request, 'imports/import_upload.html', {
            'step': '2',
            'floor': floor,
            'file_form': ExcelImportForm(),
            'back_url': reverse('floor_detail', args=[floor.pk]),
        })

    floor_form = FloorSelectForm()
    return render(request, 'imports/import_upload.html', {
        'step': '1',
        'floor_form': floor_form,
    })


def import_preview(request, pk):
    excel_import = get_object_or_404(
        ExcelImport.objects.select_related(
            'target_floor__stage__block__residential_complex__organization'
        ), pk=pk
    )

    preview_items = request.session.get('import_preview_items', [])
    total_items = request.session.get('import_parsed_items', 0)
    doc_title = request.session.get('import_doc_title', '')
    fmt = request.session.get('import_format', 'generic')

    if not preview_items:
        try:
            parsed = parse_floor_excel(excel_import.file.path)
            items = parsed.get('items', [])
            total_items = len(items)
            doc_title = parsed.get('doc_title', '')
            fmt = parsed.get('format', 'generic')
            preview_items = []
            for item in items[:20]:
                preview_items.append({
                    'item_code': item.get('item_code', ''),
                    'name': item.get('name', ''),
                    'unit': item.get('unit', ''),
                    'quantity': float(item.get('quantity', 0)),
                    'unit_price': float(item.get('unit_price', 0)),
                    'total_amount': float(item.get('total_amount', 0)),
                })
        except Exception as e:
            messages.error(request, f'Ошибка предпросмотра: {e}')
            return redirect('import_list')

    if request.method == 'POST':
        _process_floor_import(excel_import)
        messages.success(
            request,
            f'Импорт завершён: создано {excel_import.rows_processed}, '
            f'обновлено записей, ошибок {excel_import.rows_error}.'
        )
        return redirect('import_detail', pk=pk)

    zero_price_warning = preview_items and all(
        item.get('unit_price', 0) == 0 for item in preview_items
    )

    context = {
        'excel_import': excel_import,
        'floor': excel_import.target_floor,
        'preview_items': preview_items,
        'total_items': total_items,
        'doc_title': doc_title,
        'zero_price_warning': zero_price_warning,
        'format_display': {'peremeshchenie': 'Перемещение запасов (1С)',
                            'prihod': 'Приход на склад (1С)',
                            'generic': 'Общий формат'}.get(fmt, fmt),
    }
    return render(request, 'imports/import_preview.html', context)


def import_detail(request, pk):
    excel_import = get_object_or_404(
        ExcelImport.objects.select_related(
            'target_floor__stage__block__residential_complex'
        ), pk=pk
    )
    logs = excel_import.logs.all()
    return render(request, 'imports/import_detail.html',
                  {'excel_import': excel_import, 'logs': logs})


@editor_required
def import_reprocess(request, pk):
    excel_import = get_object_or_404(ExcelImport, pk=pk)
    if request.method == 'POST':
        excel_import.logs.all().delete()
        excel_import.status = 'pending'
        excel_import.rows_processed = 0
        excel_import.rows_error = 0
        excel_import.rows_total = 0
        excel_import.save()
        _process_floor_import(excel_import)
        messages.success(request, 'Импорт повторно обработан.')
    return redirect('import_detail', pk=pk)


def _process_floor_import(excel_import):
    floor = excel_import.target_floor
    if not floor:
        excel_import.status = 'error'
        excel_import.error_message = 'Не указан целевой этаж'
        excel_import.save()
        return

    excel_import.status = 'processing'
    excel_import.save(update_fields=['status'])

    try:
        parsed = parse_floor_excel(excel_import.file.path)
        items = parsed.get('items', [])
        excel_import.rows_total = len(items)

        stats = apply_floor_import(
            floor=floor,
            parsed_data=parsed,
            import_mode=excel_import.import_mode,
            excel_import=excel_import,
        )

        excel_import.rows_processed = stats['created'] + stats['updated']
        excel_import.rows_error = stats['errors']
        excel_import.status = 'completed'
        excel_import.processed_at = timezone.now()
        excel_import.save()

        ImportLog.objects.create(
            excel_import=excel_import, log_type='info',
            message=f'Формат: {parsed.get("format", "generic")} | '
                    f'Документ: {parsed.get("doc_title", "")} | '
                    f'Создано: {stats["created"]}, обновлено: {stats["updated"]}, ошибок: {stats["errors"]}'
        )

    except Exception as e:
        excel_import.status = 'error'
        excel_import.error_message = str(e)
        excel_import.save()
        ImportLog.objects.create(
            excel_import=excel_import, log_type='error',
            message=f'Критическая ошибка: {e}'
        )
