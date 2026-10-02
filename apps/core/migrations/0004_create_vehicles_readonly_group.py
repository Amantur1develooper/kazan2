from django.db import migrations


def create_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Склад авто (просмотр)')


def remove_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Склад авто (просмотр)').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_create_vehicles_group'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
