from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value


# ── Organization ──────────────────────────────────────────────────────────────

class Organization(models.Model):
    name = models.CharField('Название организации', max_length=200, unique=True)
    description = models.TextField('Описание', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Организация'
        verbose_name_plural = 'Организации'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_planned_expenses(self):
        return Stage.objects.filter(
            block__residential_complex__organization=self
        ).aggregate(
            total=Coalesce(Sum('planned_expenses'), Value(Decimal('0')))
        )['total']

    @property
    def total_actual_expenses(self):
        from_floors = FloorExpense.objects.filter(
            floor__stage__block__residential_complex__organization=self
        ).aggregate(total=Coalesce(Sum('total_amount'), Value(Decimal('0'))))['total']

        # Stages without floors use their manual actual_expenses
        manual = Stage.objects.filter(
            block__residential_complex__organization=self,
            floors__isnull=True
        ).aggregate(total=Coalesce(Sum('actual_expenses'), Value(Decimal('0'))))['total']

        return from_floors + manual

    @property
    def complexes_count(self):
        return self.complexes.count()


# ── ResidentialComplex ────────────────────────────────────────────────────────

class ResidentialComplex(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Планирование'),
        ('construction', 'Строительство'),
        ('completed', 'Завершён'),
        ('frozen', 'Заморожен'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='complexes', verbose_name='Организация'
    )
    name = models.CharField('Название ЖК', max_length=200, unique=True)
    total_planned_cost = models.DecimalField(
        'Плановая стоимость реализации', max_digits=15, decimal_places=2, default=0,
        help_text='Ожидаемая выручка от продажи объекта'
    )
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='planning')
    start_date = models.DateField('Дата начала', null=True, blank=True)
    end_date = models.DateField('Плановая сдача', null=True, blank=True)
    description = models.TextField('Описание', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Жилой комплекс'
        verbose_name_plural = 'Жилые комплексы'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_status_color(self):
        return {'planning': 'secondary', 'construction': 'primary',
                'completed': 'success', 'frozen': 'warning'}.get(self.status, 'secondary')

    @property
    def total_planned_expenses(self):
        return Stage.objects.filter(
            block__residential_complex=self
        ).aggregate(
            total=Coalesce(Sum('planned_expenses'), Value(Decimal('0')))
        )['total']

    @property
    def total_actual_expenses(self):
        from_floors = FloorExpense.objects.filter(
            floor__stage__block__residential_complex=self
        ).aggregate(total=Coalesce(Sum('total_amount'), Value(Decimal('0'))))['total']

        manual = Stage.objects.filter(
            block__residential_complex=self, floors__isnull=True
        ).aggregate(total=Coalesce(Sum('actual_expenses'), Value(Decimal('0'))))['total']

        return from_floors + manual

    @property
    def profit(self):
        return self.total_planned_cost - self.total_actual_expenses

    @property
    def deviation(self):
        return self.total_actual_expenses - self.total_planned_expenses

    @property
    def blocks_count(self):
        return self.blocks.count()


# ── Block ─────────────────────────────────────────────────────────────────────

class Block(models.Model):
    residential_complex = models.ForeignKey(
        ResidentialComplex, on_delete=models.CASCADE,
        related_name='blocks', verbose_name='Жилой комплекс'
    )
    name = models.CharField('Название блока', max_length=100,
                             help_text='Например: А, Б, В или Секция 1')
    total_budget = models.DecimalField(
        'Бюджет блока', max_digits=15, decimal_places=2, default=0
    )
    description = models.TextField('Описание', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Блок'
        verbose_name_plural = 'Блоки'
        unique_together = ['residential_complex', 'name']
        ordering = ['name']

    def __str__(self):
        return f"{self.residential_complex.name} / Блок {self.name}"

    @property
    def total_planned_expenses(self):
        return self.stages.aggregate(
            total=Coalesce(Sum('planned_expenses'), Value(Decimal('0')))
        )['total']

    @property
    def total_actual_expenses(self):
        from_floors = FloorExpense.objects.filter(
            floor__stage__block=self
        ).aggregate(total=Coalesce(Sum('total_amount'), Value(Decimal('0'))))['total']

        manual = self.stages.filter(floors__isnull=True).aggregate(
            total=Coalesce(Sum('actual_expenses'), Value(Decimal('0')))
        )['total']

        return from_floors + manual

    @property
    def deviation(self):
        return self.total_actual_expenses - self.total_planned_expenses

    @property
    def stages_count(self):
        return self.stages.count()


# ── Stage ─────────────────────────────────────────────────────────────────────

class Stage(models.Model):
    block = models.ForeignKey(
        Block, on_delete=models.CASCADE,
        related_name='stages', verbose_name='Блок'
    )
    name = models.CharField('Название этапа', max_length=200)
    planned_expenses = models.DecimalField(
        'Плановые расходы (смета)', max_digits=15, decimal_places=2, default=0
    )
    actual_expenses = models.DecimalField(
        'Фактические расходы (вручную)', max_digits=15, decimal_places=2, default=0,
        help_text='Используется только если этажи не добавлены'
    )
    order = models.PositiveIntegerField('Порядок', default=0)
    description = models.TextField('Описание', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Этап'
        verbose_name_plural = 'Этапы'
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.block} / {self.name}"

    @property
    def has_floors(self):
        return self.floors.exists()

    @property
    def computed_actual_expenses(self):
        if self.has_floors:
            return FloorExpense.objects.filter(
                floor__stage=self
            ).aggregate(
                total=Coalesce(Sum('total_amount'), Value(Decimal('0')))
            )['total']
        return self.actual_expenses

    @property
    def deviation(self):
        return self.computed_actual_expenses - self.planned_expenses

    @property
    def deviation_percent(self):
        if self.planned_expenses > 0:
            return float((self.deviation / self.planned_expenses) * 100)
        return 0.0

    @property
    def completion_percent(self):
        if self.planned_expenses > 0:
            val = float((self.computed_actual_expenses / self.planned_expenses) * 100)
            return min(val, 100)
        return 0.0

    @property
    def floors_count(self):
        return self.floors.count()


# ── Floor ─────────────────────────────────────────────────────────────────────

class Floor(models.Model):
    stage = models.ForeignKey(
        Stage, on_delete=models.CASCADE,
        related_name='floors', verbose_name='Этап'
    )
    number = models.IntegerField('Номер этажа')
    name = models.CharField('Название / описание', max_length=100, blank=True,
                             help_text='Необязательно. Например: "Цокольный", "Технический"')
    description = models.TextField('Примечание', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Этаж'
        verbose_name_plural = 'Этажи'
        unique_together = ['stage', 'number']
        ordering = ['number']

    def __str__(self):
        suffix = f' ({self.name})' if self.name else ''
        return f"{self.stage} / Этаж {self.number}{suffix}"

    @property
    def display_name(self):
        return self.name or f"Этаж {self.number}"

    @property
    def total_expenses(self):
        return self.expenses.aggregate(
            total=Coalesce(Sum('total_amount'), Value(Decimal('0')))
        )['total']

    @property
    def expenses_count(self):
        return self.expenses.count()


# ── FloorExpense ──────────────────────────────────────────────────────────────

class FloorExpense(models.Model):
    floor = models.ForeignKey(
        Floor, on_delete=models.CASCADE,
        related_name='expenses', verbose_name='Этаж'
    )
    item_code = models.CharField('Код номенклатуры', max_length=50, blank=True,
                                  help_text='Например: НФ-00000130')
    name = models.CharField('Наименование', max_length=400)
    unit = models.CharField('Единица измерения', max_length=30, blank=True)
    quantity = models.DecimalField('Количество', max_digits=15, decimal_places=3, default=0)
    unit_price = models.DecimalField('Цена за единицу', max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField('Сумма', max_digits=15, decimal_places=2, default=0)

    source_import = models.ForeignKey(
        'imports.ExcelImport', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='created_expenses',
        verbose_name='Источник (импорт)'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Расход этажа'
        verbose_name_plural = 'Расходы этажа'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} — {self.total_amount}"

    def save(self, *args, **kwargs):
        # Auto-compute total if unit_price set
        if self.unit_price and self.quantity and self.total_amount == 0:
            self.total_amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)
