from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planfact', '0014_avritem_estimate_item'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BuilderProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plain_password', models.CharField(blank=True, default='', max_length=128, verbose_name='Пароль')),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='builder_profile',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Пользователь',
                )),
            ],
            options={
                'verbose_name': 'Профиль строителя',
                'verbose_name_plural': 'Профили строителей',
            },
        ),
    ]
