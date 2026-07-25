from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estimates', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='estimateitem',
            name='code',
            field=models.CharField(blank=True, max_length=20, verbose_name='Код'),
        ),
    ]
