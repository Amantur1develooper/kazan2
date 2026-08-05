from decimal import Decimal
from django.db import models
from django.db.models import Sum


class CashAccount(models.Model):
    ACCOUNT_TYPES = [
        ('cash', 'Касса'),
        ('bank', 'Банк'),
    ]
    name = models.CharField('Название', max_length=255)
    account_type = models.CharField('Тип', max_length=10, choices=ACCOUNT_TYPES, default='cash')
    residential_complex = models.ForeignKey(
        'projects.ResidentialComplex', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cash_accounts',
        verbose_name='ЖК'
    )
    block = models.ForeignKey(
        'projects.Block', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cash_accounts',
        verbose_name='Блок'
    )
    notes = models.TextField('Заметки', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Касса / счёт'
        verbose_name_plural = 'Кассы / счета'
        ordering = ['residential_complex__name', 'name']

    def __str__(self):
        return self.name

    @property
    def balance(self):
        income = self.records.filter(direction='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')
        expense = self.records.filter(direction='out').aggregate(s=Sum('amount'))['s'] or Decimal('0')
        return income - expense

    @property
    def total_income(self):
        return self.records.filter(direction='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    @property
    def total_expense(self):
        return self.records.filter(direction='out').aggregate(s=Sum('amount'))['s'] or Decimal('0')


class DDSImport(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('processing', 'Обрабатывается'),
        ('completed', 'Завершён'),
        ('error', 'Ошибка'),
    ]
    file = models.FileField('Файл', upload_to='dds/%Y/%m/')
    original_filename = models.CharField('Имя файла', max_length=255)
    residential_complex = models.ForeignKey(
        'projects.ResidentialComplex', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='dds_imports',
        verbose_name='ЖК'
    )
    block = models.ForeignKey(
        'projects.Block', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='dds_imports',
        verbose_name='Блок'
    )
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='pending')
    rows_total = models.IntegerField('Всего строк', default=0)
    rows_processed = models.IntegerField('Обработано', default=0)
    rows_error = models.IntegerField('Ошибок', default=0)
    error_message = models.TextField('Сообщение об ошибке', blank=True)
    uploaded_at = models.DateTimeField('Загружен', auto_now_add=True)
    processed_at = models.DateTimeField('Обработан', null=True, blank=True)

    class Meta:
        verbose_name = 'Импорт ДДС'
        verbose_name_plural = 'Импорты ДДС'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at:%d.%m.%Y %H:%M})"


class CashFlowRecord(models.Model):
    DIRECTION_CHOICES = [
        ('in', 'Приход'),
        ('out', 'Расход'),
        ('transfer', 'Перемещение'),
    ]

    operation_date = models.DateField('Дата')
    bank_or_cash = models.CharField('Банк/Касса', max_length=50, blank=True)
    operation_type = models.CharField('Тип операции', max_length=100)
    direction = models.CharField('Направление', max_length=10, choices=DIRECTION_CHOICES)
    amount = models.DecimalField('Сумма', max_digits=15, decimal_places=2, default=0)
    transfer_amount = models.DecimalField('Сумма перемещения', max_digits=15, decimal_places=2, default=0)
    counterparty = models.CharField('Контрагент', max_length=255, blank=True)
    account_name = models.CharField('Счёт (1С)', max_length=255, blank=True)
    object_ref = models.CharField('Объект (1С)', max_length=255, blank=True)
    description = models.CharField('Назначение', max_length=500, blank=True)

    # Linked objects (set during distribution)
    account = models.ForeignKey(
        CashAccount, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='records',
        verbose_name='Касса'
    )
    block = models.ForeignKey(
        'projects.Block', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='dds_records',
        verbose_name='Блок'
    )
    estimate_item = models.ForeignKey(
        'estimates.EstimateItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='dds_records',
        verbose_name='Позиция сметы'
    )
    source_import = models.ForeignKey(
        DDSImport, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='records',
        verbose_name='Импорт'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Запись ДДС'
        verbose_name_plural = 'Записи ДДС'
        ordering = ['-operation_date', '-created_at']

    def __str__(self):
        direction_label = {'in': '↑', 'out': '↓', 'transfer': '⇄'}.get(self.direction, '')
        return f"{self.operation_date} {direction_label} {self.amount} | {self.operation_type}"
