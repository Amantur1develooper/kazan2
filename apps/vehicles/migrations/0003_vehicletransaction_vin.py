from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0002_vehicletransaction_is_sold'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicletransaction',
            name='vin',
            field=models.CharField(blank=True, max_length=17, verbose_name='VIN номер'),
        ),
    ]
