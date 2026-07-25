from django.db import migrations, models


def populate_stable_keys(apps, schema_editor):
    EstimateItem = apps.get_model('estimates', 'EstimateItem')
    items = EstimateItem.objects.select_related('section__estimate__block').filter(
        section__estimate__block__isnull=False
    )
    to_update = []
    for item in items:
        block_id = item.section.estimate.block_id
        code = item.code or item.name[:80]
        item.stable_key = f'{block_id}:{code}'
        to_update.append(item)
    if to_update:
        EstimateItem.objects.bulk_update(to_update, ['stable_key'])


class Migration(migrations.Migration):

    dependencies = [
        ('estimates', '0005_estimateitemexpenselink'),
    ]

    operations = [
        migrations.AddField(
            model_name='estimateitem',
            name='stable_key',
            field=models.CharField(blank=True, db_index=True, max_length=100, verbose_name='Стабильный ключ'),
        ),
        migrations.RunPython(populate_stable_keys, migrations.RunPython.noop),
    ]
