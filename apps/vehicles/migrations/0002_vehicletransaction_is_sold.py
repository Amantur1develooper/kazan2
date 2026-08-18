from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicletransaction',
            name='is_sold',
            field=models.BooleanField(default=False, verbose_name='Продана'),
        ),
    ]
