from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('estimates', '0003_estimateversion_estimatechangelog'),
    ]

    operations = [
        migrations.AddField(
            model_name='estimateitem',
            name='is_modified',
            field=models.BooleanField(default=False, verbose_name='Изменён вручную'),
        ),
        migrations.AddField(
            model_name='estimateitem',
            name='modified_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Дата изменения'),
        ),
        migrations.CreateModel(
            name='EstimateItemHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('changed_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата изменения')),
                ('field_name', models.CharField(max_length=50, verbose_name='Поле')),
                ('old_value', models.CharField(blank=True, max_length=300, verbose_name='Было')),
                ('new_value', models.CharField(blank=True, max_length=300, verbose_name='Стало')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='estimates.estimateitem', verbose_name='Позиция')),
            ],
            options={
                'verbose_name': 'История изменения позиции',
                'verbose_name_plural': 'История изменений позиций',
                'ordering': ['-changed_at'],
            },
        ),
    ]
