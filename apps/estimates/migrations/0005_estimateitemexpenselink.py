from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('estimates', '0004_estimateitem_modified_estimateitemhistory'),
    ]

    operations = [
        migrations.CreateModel(
            name='EstimateItemExpenseLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('expense_name', models.CharField(max_length=400, verbose_name='Наименование расхода (ПФ)')),
                ('estimate_item', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='expense_links',
                    to='estimates.estimateitem',
                    verbose_name='Позиция сметы',
                )),
            ],
            options={
                'verbose_name': 'Привязка расхода к позиции',
                'verbose_name_plural': 'Привязки расходов к позициям',
            },
        ),
        migrations.AlterUniqueTogether(
            name='estimateitemexpenselink',
            unique_together={('estimate_item', 'expense_name')},
        ),
    ]
