"""
0008: two-step data migration
  a) Recompute stable_key to include item name (fixes 30 duplicate keys)
  b) Transfer EstimateItemExpenseLink → ExpenseAllocation (idempotent, 100% qty)
"""
from django.db import migrations
from decimal import Decimal


def fix_stable_keys(apps, schema_editor):
    EstimateItem = apps.get_model('estimates', 'EstimateItem')
    updated = 0
    for item in EstimateItem.objects.select_related('section__estimate__block').iterator(chunk_size=500):
        block_id = item.section.estimate.block_id
        code = item.code or ''
        name = item.name or ''
        if code:
            new_key = f'{block_id}:{code}:{name[:60]}'
        else:
            new_key = f'{block_id}:{name[:80]}'
        if item.stable_key != new_key:
            item.stable_key = new_key
            item.save(update_fields=['stable_key'])
            updated += 1
    print(f'  fix_stable_keys: updated {updated} rows')


def migrate_expense_links(apps, schema_editor):
    EstimateItemExpenseLink = apps.get_model('estimates', 'EstimateItemExpenseLink')
    ExpenseAllocation = apps.get_model('estimates', 'ExpenseAllocation')
    FloorExpense = apps.get_model('projects', 'FloorExpense')

    links = list(
        EstimateItemExpenseLink.objects
        .select_related('estimate_item__section__estimate__block')
        .all()
    )

    created = skipped = not_found = 0

    for link in links:
        item = link.estimate_item
        block = item.section.estimate.block
        expense_name = link.expense_name

        # Find all FloorExpense with this name in the block
        expenses = FloorExpense.objects.filter(
            name=expense_name,
            floor__stage__block=block,
        )

        if not expenses.exists():
            not_found += 1
            continue

        for fe in expenses:
            obj, was_created = ExpenseAllocation.objects.get_or_create(
                floor_expense=fe,
                estimate_item=item,
                defaults={
                    'quantity': fe.quantity,
                    'amount': fe.total_amount,
                    'note': f'Перенесено из EstimateItemExpenseLink #{link.pk}',
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1

    print(f'  migrate_expense_links: created={created} skipped={skipped} not_found={not_found}')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('estimates', '0007_expenseallocation'),
        ('projects', '0005_floorexpense_nomenclature'),
    ]

    operations = [
        migrations.RunPython(fix_stable_keys, noop),
        migrations.RunPython(migrate_expense_links, noop),
    ]
