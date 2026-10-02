from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0004_vehicletransaction_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicletransaction',
            name='image_passport',
            field=models.ImageField(blank=True, null=True, upload_to='vehicles/passports/', verbose_name='Фото тех. паспорта'),
        ),
    ]
