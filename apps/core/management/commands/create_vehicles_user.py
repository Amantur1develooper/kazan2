from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


class Command(BaseCommand):
    help = 'Создать пользователя с доступом только к разделу «Склад авто»'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)
        parser.add_argument('password', type=str)

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name='Склад авто')

        username = options['username']
        password = options['password']

        if User.objects.filter(username=username).exists():
            user = User.objects.get(username=username)
            user.set_password(password)
            user.save()
            self.stdout.write(f'Пользователь «{username}» обновлён.')
        else:
            user = User.objects.create_user(username=username, password=password)
            self.stdout.write(f'Пользователь «{username}» создан.')

        user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(
            f'Готово. Логин: {username} | Группа: Склад авто | Доступ: /vehicles/'
        ))
