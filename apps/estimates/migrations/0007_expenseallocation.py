from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('estimates', '0006_estimateitem_stable_key'),
        ('projects', '0005_floorexpense_nomenclature'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpenseAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=3, default=0, max_digits=14, verbose_name='Количество')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Сумма')),
                ('note', models.CharField(blank=True, max_length=200, verbose_name='Примечание')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('floor_expense', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='allocations',
                    to='projects.floorexpense',
                    verbose_name='Расход',
                )),
                ('estimate_item', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='allocations',
                    to='estimates.estimateitem',
                    verbose_name='Позиция сметы',
                )),
            ],
            options={
                'verbose_name': 'Аллокация расхода',
                'verbose_name_plural': 'Аллокации расходов',
            },
        ),
        migrations.AddConstraint(
            model_name='expenseallocation',
            constraint=models.UniqueConstraint(
                fields=['floor_expense', 'estimate_item'],
                name='unique_expense_item_allocation',
            ),
        ),
    ]
