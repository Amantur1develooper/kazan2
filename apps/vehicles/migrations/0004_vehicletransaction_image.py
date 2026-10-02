from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0003_vehicletransaction_vin'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicletransaction',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='vehicles/', verbose_name='Фото'),
        ),
    ]
