from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planfact', '0011_asm_acceptance'),
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FloorLabel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('floor_number', models.IntegerField(verbose_name='Номер этажа')),
                ('label', models.CharField(blank=True, max_length=100, verbose_name='Название этажа')),
                ('block', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='floor_labels', to='projects.block', verbose_name='Блок')),
            ],
            options={
                'verbose_name': 'Название этажа',
                'verbose_name_plural': 'Названия этажей',
                'ordering': ['floor_number'],
                'unique_together': {('block', 'floor_number')},
            },
        ),
    ]
