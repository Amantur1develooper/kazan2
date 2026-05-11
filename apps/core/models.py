from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value


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
