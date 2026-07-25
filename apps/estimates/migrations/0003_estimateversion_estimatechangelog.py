from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('estimates', '0002_estimateitem_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='EstimateVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imported_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата импорта')),
                ('source_file', models.CharField(blank=True, max_length=255, verbose_name='Файл')),
                ('total_before', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Итого до')),
                ('total_after', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Итого после')),
                ('sections_count', models.PositiveIntegerField(default=0, verbose_name='Разделов')),
                ('items_count', models.PositiveIntegerField(default=0, verbose_name='Позиций')),
                ('items_added', models.PositiveIntegerField(default=0, verbose_name='Добавлено')),
                ('items_updated', models.PositiveIntegerField(default=0, verbose_name='Изменено')),
                ('items_removed', models.PositiveIntegerField(default=0, verbose_name='Удалено')),
                ('estimate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='estimates.estimate', verbose_name='Смета')),
            ],
            options={
                'verbose_name': 'Версия сметы',
                'verbose_name_plural': 'Версии сметы',
                'ordering': ['-imported_at'],
            },
        ),
        migrations.CreateModel(
            name='EstimateChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('added', 'Добавлено'), ('updated', 'Изменено'), ('removed', 'Удалено')], max_length=10, verbose_name='Действие')),
                ('item_code', models.CharField(blank=True, max_length=20, verbose_name='Код')),
                ('item_name', models.CharField(max_length=400, verbose_name='Наименование')),
                ('field_name', models.CharField(blank=True, max_length=50, verbose_name='Поле')),
                ('old_value', models.CharField(blank=True, max_length=200, verbose_name='Было')),
                ('new_value', models.CharField(blank=True, max_length=200, verbose_name='Стало')),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='changes', to='estimates.estimateversion', verbose_name='Версия')),
            ],
            options={
                'verbose_name': 'Изменение сметы',
                'verbose_name_plural': 'Изменения сметы',
                'ordering': ['action', 'item_code'],
            },
        ),
    ]
