from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value


class NomenclatureGroup(models.Model):
    name = models.CharField('Группа', max_length=200, unique=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Группа номенклатуры'
        verbose_name_plural = 'Группы номенклатуры'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Nomenclature(models.Model):
    code_1c = models.CharField('Код 1С', max_length=50, blank=True)
    name = models.CharField('Наименование', max_length=400, unique=True)
    unit = models.CharField('Ед. изм.', max_length=30, blank=True)
    group = models.ForeignKey(
        NomenclatureGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='items', verbose_name='Группа'
    )
    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Номенклатура'
        verbose_name_plural = 'Номенклатура'
        ordering = ['name']

    def __str__(self):
        return self.name


class NomenclatureAlias(models.Model):
    nomenclature = models.ForeignKey(
        Nomenclature, on_delete=models.CASCADE,
        related_name='aliases', verbose_name='Номенклатура'
    )
    alias_name = models.CharField('Псевдоним', max_length=400, unique=True)

    class Meta:
        verbose_name = 'Псевдоним номенклатуры'
        verbose_name_plural = 'Псевдонимы номенклатуры'

    def __str__(self):
        return f'{self.alias_name} → {self.nomenclature.name}'


class Estimate(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('active', 'Активна'),
        ('archived', 'Архив'),
    ]
    block = models.OneToOneField(
        'projects.Block', on_delete=models.CASCADE,
        related_name='estimate', verbose_name='Блок'
    )
    name = models.CharField('Название', max_length=200, blank=True)
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='draft')
    total_amount = models.DecimalField('Итого по смете', max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Смета'
        verbose_name_plural = 'Сметы'

    def __str__(self):
        return f'Смета: {self.block}'

    def recalculate_total(self):
        total = self.sections.filter(parent__isnull=True).aggregate(
            t=Coalesce(Sum('total_amount'), Value(Decimal('0')))
        )['t']
        self.total_amount = total
        self.save(update_fields=['total_amount', 'updated_at'])


class EstimateSection(models.Model):
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE,
        related_name='sections', verbose_name='Смета'
    )
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE,
        related_name='children', verbose_name='Родительский раздел'
    )
    name = models.CharField('Название', max_length=400)
    code = models.CharField('Код', max_length=20, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    total_amount = models.DecimalField('Итого (план)', max_digits=15, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Раздел сметы'
        verbose_name_plural = 'Разделы сметы'
        ordering = ['order', 'code']

    def __str__(self):
        return f'{self.code} {self.name}'

    def recalculate(self):
        items_total = self.items.aggregate(
            t=Coalesce(Sum('total_amount'), Value(Decimal('0')))
        )['t']
        children_total = self.children.aggregate(
            t=Coalesce(Sum('total_amount'), Value(Decimal('0')))
        )['t']
        self.total_amount = items_total + children_total
        self.save(update_fields=['total_amount'])
        if self.parent_id:
            self.parent.recalculate()


class EstimateItem(models.Model):
    section = models.ForeignKey(
        EstimateSection, on_delete=models.CASCADE,
        related_name='items', verbose_name='Раздел'
    )
    nomenclature = models.ForeignKey(
        Nomenclature, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='estimate_items', verbose_name='Номенклатура'
    )
    code = models.CharField('Код', max_length=20, blank=True)
    name = models.CharField('Наименование', max_length=400)
    unit = models.CharField('Ед. изм.', max_length=30, blank=True)
    quantity = models.DecimalField('Количество', max_digits=15, decimal_places=3, default=0)
    unit_price = models.DecimalField('Цена за ед.', max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField('Сумма (план)', max_digits=15, decimal_places=2, default=0)
    note = models.CharField('Примечание', max_length=300, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    is_modified = models.BooleanField('Изменён вручную', default=False)
    modified_at = models.DateTimeField('Дата изменения', null=True, blank=True)
    stable_key = models.CharField('Стабильный ключ', max_length=100, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Позиция сметы'
        verbose_name_plural = 'Позиции сметы'
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.name} — {self.total_amount}'


class EstimateItemHistory(models.Model):
    FIELD_LABELS = {
        'quantity': 'Количество',
        'unit_price': 'Цена',
        'total_amount': 'Сумма',
        'name': 'Наименование',
        'unit': 'Ед. изм.',
        'note': 'Примечание',
    }
    item = models.ForeignKey(
        EstimateItem, on_delete=models.CASCADE,
        related_name='history', verbose_name='Позиция'
    )
    changed_at = models.DateTimeField('Дата изменения', auto_now_add=True)
    field_name = models.CharField('Поле', max_length=50)
    old_value = models.CharField('Было', max_length=300, blank=True)
    new_value = models.CharField('Стало', max_length=300, blank=True)

    class Meta:
        verbose_name = 'История изменения позиции'
        verbose_name_plural = 'История изменений позиций'
        ordering = ['-changed_at']

    def get_field_label(self):
        return self.FIELD_LABELS.get(self.field_name, self.field_name)


class EstimateItemExpenseLink(models.Model):
    estimate_item = models.ForeignKey(
        EstimateItem, on_delete=models.CASCADE,
        related_name='expense_links', verbose_name='Позиция сметы'
    )
    expense_name = models.CharField('Наименование расхода (ПФ)', max_length=400)

    class Meta:
        verbose_name = 'Привязка расхода к позиции'
        verbose_name_plural = 'Привязки расходов к позициям'
        unique_together = ['estimate_item', 'expense_name']

    def __str__(self):
        return f'{self.expense_name} → {self.estimate_item.name}'


class ExpenseAllocation(models.Model):
    floor_expense = models.ForeignKey(
        'projects.FloorExpense', on_delete=models.CASCADE,
        related_name='allocations', verbose_name='Расход'
    )
    estimate_item = models.ForeignKey(
        EstimateItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='allocations', verbose_name='Позиция сметы'
    )
    quantity = models.DecimalField('Количество', max_digits=14, decimal_places=3, default=0)
    amount = models.DecimalField('Сумма', max_digits=14, decimal_places=2, default=0)
    note = models.CharField('Примечание', max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Аллокация расхода'
        verbose_name_plural = 'Аллокации расходов'
        constraints = [
            models.UniqueConstraint(
                fields=['floor_expense', 'estimate_item'],
                name='unique_expense_item_allocation'
            )
        ]

    def __str__(self):
        item_name = self.estimate_item.name if self.estimate_item else 'Нераспределено'
        return f'{self.floor_expense.name} → {item_name}'


class EstimateVersion(models.Model):
    estimate = models.ForeignKey(
        Estimate, on_delete=models.CASCADE,
        related_name='versions', verbose_name='Смета'
    )
    imported_at = models.DateTimeField('Дата импорта', auto_now_add=True)
    source_file = models.CharField('Файл', max_length=255, blank=True)
    total_before = models.DecimalField('Итого до', max_digits=15, decimal_places=2, default=0)
    total_after = models.DecimalField('Итого после', max_digits=15, decimal_places=2, default=0)
    sections_count = models.PositiveIntegerField('Разделов', default=0)
    items_count = models.PositiveIntegerField('Позиций', default=0)
    items_added = models.PositiveIntegerField('Добавлено', default=0)
    items_updated = models.PositiveIntegerField('Изменено', default=0)
    items_removed = models.PositiveIntegerField('Удалено', default=0)

    class Meta:
        verbose_name = 'Версия сметы'
        verbose_name_plural = 'Версии сметы'
        ordering = ['-imported_at']

    def __str__(self):
        return f'Версия {self.imported_at:%d.%m.%Y %H:%M} — {self.estimate}'


class EstimateChangeLog(models.Model):
    ACTION_CHOICES = [
        ('added', 'Добавлено'),
        ('updated', 'Изменено'),
        ('removed', 'Удалено'),
    ]
    version = models.ForeignKey(
        EstimateVersion, on_delete=models.CASCADE,
        related_name='changes', verbose_name='Версия'
    )
    action = models.CharField('Действие', max_length=10, choices=ACTION_CHOICES)
    item_code = models.CharField('Код', max_length=20, blank=True)
    item_name = models.CharField('Наименование', max_length=400)
    field_name = models.CharField('Поле', max_length=50, blank=True)
    old_value = models.CharField('Было', max_length=200, blank=True)
    new_value = models.CharField('Стало', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Изменение сметы'
        verbose_name_plural = 'Изменения сметы'
        ordering = ['action', 'item_code']

    def __str__(self):
        return f'{self.get_action_display()} {self.item_code} {self.item_name[:40]}'


class ExtraBlockExpense(models.Model):
    """Расходы не входящие в смету — учитываются в расчёте маржи блока."""
    block = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='extra_expenses', verbose_name='Блок'
    )
    name = models.CharField('Статья расхода', max_length=255)
    amount = models.DecimalField('Сумма', max_digits=15, decimal_places=2)
    date = models.DateField('Дата', null=True, blank=True)
    description = models.TextField('Примечание', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Внесметный расход'
        verbose_name_plural = 'Внесметные расходы'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.name} — {self.amount}'
