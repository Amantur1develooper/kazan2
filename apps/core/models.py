from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value


class CompanyDirector(models.Model):
    name        = models.CharField('Имя и фамилия', max_length=200, default='Аман Тюреркинов')
    position    = models.CharField('Должность', max_length=100, default='Генеральный директор / CEO')
    photo       = models.ImageField('Фото', upload_to='director/', blank=True, null=True)
    phone       = models.CharField('Телефон', max_length=50, blank=True, default='0558212040')
    email       = models.EmailField('Email', blank=True, default='amanturagency@gmail.com')
    bio         = models.TextField('О себе', blank=True)
    company     = models.CharField('Компания', max_length=200, blank=True, default='Строй Финанс')

    class Meta:
        verbose_name = 'Директор / CEO'
        verbose_name_plural = 'Директор / CEO'

    def __str__(self):
        return self.name

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class MainCash(models.Model):
    name = models.CharField('Название', max_length=100, default='Главная касса')
    description = models.TextField('Описание', blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Главная касса'
        verbose_name_plural = 'Главная касса'

    def __str__(self):
        return self.name

    @property
    def total_income(self):
        return self.transactions.filter(
            transaction_type='income'
        ).aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0')))
        )['total']

    @property
    def total_expense(self):
        return self.transactions.filter(
            transaction_type='expense'
        ).aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0')))
        )['total']

    @property
    def current_balance(self):
        return self.total_income - self.total_expense


class CashTransaction(models.Model):
    TYPES = [
        ('income', 'Приход'),
        ('expense', 'Расход'),
    ]

    main_cash = models.ForeignKey(
        MainCash, on_delete=models.CASCADE,
        related_name='transactions', verbose_name='Касса'
    )
    transaction_type = models.CharField('Тип', max_length=10, choices=TYPES)
    amount = models.DecimalField('Сумма', max_digits=15, decimal_places=2)
    description = models.CharField('Описание', max_length=500)
    date = models.DateField('Дата')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Транзакция'
        verbose_name_plural = 'Транзакции'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount} — {self.description}"
