import xlrd
from django.core.management.base import BaseCommand
from apps.estimates.models import Nomenclature


class Command(BaseCommand):
    help = 'Import nomenclature from Excel file'

    def add_arguments(self, parser):
        parser.add_argument('filepath', type=str, help='Path to .xls file')

    def handle(self, *args, **options):
        path = options['filepath']
        wb = xlrd.open_workbook(path)
        ws = wb.sheet_by_index(0)

        created = updated = skipped = 0
        seen = set()

        for i in range(1, ws.nrows):
            name = str(ws.cell_value(i, 0)).strip()
            unit = str(ws.cell_value(i, 3)).strip()
            if not name or name in seen:
                skipped += 1
                continue
            seen.add(name)
            obj, new = Nomenclature.objects.update_or_create(
                name=name,
                defaults={'unit': unit, 'is_active': True},
            )
            if new:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Готово: создано {created}, обновлено {updated}, пропущено {skipped}'
        ))
