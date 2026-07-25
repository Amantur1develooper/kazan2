from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NomenclatureGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True, verbose_name='Группа')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
            ],
            options={
                'verbose_name': 'Группа номенклатуры',
                'verbose_name_plural': 'Группы номенклатуры',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Nomenclature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_1c', models.CharField(blank=True, max_length=50, verbose_name='Код 1С')),
                ('name', models.CharField(max_length=400, unique=True, verbose_name='Наименование')),
                ('unit', models.CharField(blank=True, max_length=30, verbose_name='Ед. изм.')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='items', to='estimates.nomenclaturegroup', verbose_name='Группа')),
            ],
            options={
                'verbose_name': 'Номенклатура',
                'verbose_name_plural': 'Номенклатура',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='NomenclatureAlias',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias_name', models.CharField(max_length=400, unique=True, verbose_name='Псевдоним')),
                ('nomenclature', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aliases', to='estimates.nomenclature', verbose_name='Номенклатура')),
            ],
            options={
                'verbose_name': 'Псевдоним номенклатуры',
                'verbose_name_plural': 'Псевдонимы номенклатуры',
            },
        ),
        migrations.CreateModel(
            name='Estimate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=200, verbose_name='Название')),
                ('status', models.CharField(choices=[('draft', 'Черновик'), ('active', 'Активна'), ('archived', 'Архив')], default='draft', max_length=20, verbose_name='Статус')),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Итого по смете')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('block', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='estimate', to='projects.block', verbose_name='Блок')),
            ],
            options={
                'verbose_name': 'Смета',
                'verbose_name_plural': 'Сметы',
            },
        ),
        migrations.CreateModel(
            name='EstimateSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=400, verbose_name='Название')),
                ('code', models.CharField(blank=True, max_length=20, verbose_name='Код')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Итого (план)')),
                ('estimate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='estimates.estimate', verbose_name='Смета')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='estimates.estimatesection', verbose_name='Родительский раздел')),
            ],
            options={
                'verbose_name': 'Раздел сметы',
                'verbose_name_plural': 'Разделы сметы',
                'ordering': ['order', 'code'],
            },
        ),
        migrations.CreateModel(
            name='EstimateItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=400, verbose_name='Наименование')),
                ('unit', models.CharField(blank=True, max_length=30, verbose_name='Ед. изм.')),
                ('quantity', models.DecimalField(decimal_places=3, default=0, max_digits=15, verbose_name='Количество')),
                ('unit_price', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Цена за ед.')),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Сумма (план)')),
                ('note', models.CharField(blank=True, max_length=300, verbose_name='Примечание')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
                ('nomenclature', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='estimate_items', to='estimates.nomenclature', verbose_name='Номенклатура')),
                ('section', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='estimates.estimatesection', verbose_name='Раздел')),
            ],
            options={
                'verbose_name': 'Позиция сметы',
                'verbose_name_plural': 'Позиции сметы',
                'ordering': ['order', 'name'],
            },
        ),
    ]
