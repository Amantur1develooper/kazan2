from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0004_add_square_meters_to_complex'),
        ('estimates', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='floorexpense',
            name='nomenclature',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='floor_expenses',
                to='estimates.nomenclature',
                verbose_name='Номенклатура',
            ),
        ),
    ]
