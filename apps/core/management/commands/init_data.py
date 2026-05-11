from django.core.management.base import BaseCommand
from apps.core.models import MainCash
from apps.projects.models import Organization, ResidentialComplex


class Command(BaseCommand):
    help = 'Initialize required base data'

    def handle(self, *args, **options):
        # Main cash
        if not MainCash.objects.exists():
            MainCash.objects.create(name='Главная касса', description='Основная касса компании')
            self.stdout.write(self.style.SUCCESS('✓ Главная касса создана'))
        else:
            self.stdout.write('  Главная касса уже существует')

        # Default organization
        org, created = Organization.objects.get_or_create(
            name='Основная организация',
            defaults={'description': 'Организация по умолчанию'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Организация создана'))
        else:
            self.stdout.write('  Организация уже существует')

        # Assign orphaned complexes to default org
        orphaned = ResidentialComplex.objects.filter(organization__isnull=True)
        count = orphaned.update(organization=org)
        if count:
            self.stdout.write(self.style.SUCCESS(f'✓ {count} ЖК привязаны к организации'))
