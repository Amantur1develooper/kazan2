from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User

MONTHS_RU = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
              'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
MONTHS_SHORT = ['', 'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']


class WorkCategory(models.Model):
    SCOPE_CHOICES = [
        ('floor', 'По этажам'),
        ('landscaping', 'Благоустройство'),
        ('general', 'Общее'),
    ]
    name = models.CharField('Название', max_length=100)
    unit = models.CharField('Единица изм.', max_length=20, default='м²')
    scope = models.CharField('Область', max_length=20, choices=SCOPE_CHOICES, default='floor')
    color = models.CharField('Цвет (hex)', max_length=7, default='#3b82f6')
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Вид работ'
        verbose_name_plural = 'Виды работ'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class BlockFloorConfig(models.Model):
    block = models.OneToOneField(
        'projects.Block', on_delete=models.CASCADE,
        related_name='floor_config', verbose_name='Блок'
    )
    total_floors = models.PositiveIntegerField('Всего этажей', default=1)
    underground_floors = models.PositiveIntegerField('Подземных этажей', default=0)
    has_landscaping = models.BooleanField('Есть благоустройство', default=True)

    class Meta:
        verbose_name = 'Конфигурация этажей блока'
        verbose_name_plural = 'Конфигурации этажей'

    def __str__(self):
        return f"Блок {self.block.name} — {self.total_floors} эт."


class FloorWork(models.Model):
    block = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='floor_works', verbose_name='Блок'
    )
    floor_number = models.IntegerField('Номер этажа')
    category = models.ForeignKey(
        WorkCategory, on_delete=models.CASCADE,
        related_name='floor_works', verbose_name='Вид работ'
    )
    planned_quantity = models.DecimalField('План кол-во', max_digits=12, decimal_places=2, default=0)
    planned_amount   = models.DecimalField('План сумма',  max_digits=15, decimal_places=2, default=0)
    fact_quantity    = models.DecimalField('Факт кол-во', max_digits=12, decimal_places=2, default=0)
    fact_amount      = models.DecimalField('Факт сумма',  max_digits=15, decimal_places=2, default=0)
    fact_date        = models.DateField('Дата факта', null=True, blank=True)
    contractor       = models.CharField('Подрядчик', max_length=200, blank=True)
    notes            = models.TextField('Примечание', blank=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='floor_work_updates', verbose_name='Обновил'
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Работа по этажу'
        verbose_name_plural = 'Работы по этажам'
        unique_together = ['block', 'floor_number', 'category']
        ordering = ['floor_number', 'category__order']

    def __str__(self):
        return f"Блок {self.block.name} / Эт.{self.floor_number} / {self.category.name}"

    @property
    def progress_pct(self):
        if self.planned_quantity > 0:
            return min(100, round(float(self.fact_quantity / self.planned_quantity * 100), 1))
        return 0


class LandscapingWork(models.Model):
    block = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='landscaping_works', verbose_name='Блок'
    )
    category = models.ForeignKey(
        WorkCategory, on_delete=models.CASCADE,
        related_name='landscaping_works', verbose_name='Вид работ'
    )
    planned_quantity = models.DecimalField('План кол-во', max_digits=12, decimal_places=2, default=0)
    planned_amount   = models.DecimalField('План сумма',  max_digits=15, decimal_places=2, default=0)
    fact_quantity    = models.DecimalField('Факт кол-во', max_digits=12, decimal_places=2, default=0)
    fact_amount      = models.DecimalField('Факт сумма',  max_digits=15, decimal_places=2, default=0)
    fact_date        = models.DateField('Дата факта', null=True, blank=True)
    contractor       = models.CharField('Подрядчик', max_length=200, blank=True)
    notes            = models.TextField('Примечание', blank=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='landscaping_updates', verbose_name='Обновил'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Работа по благоустройству'
        verbose_name_plural = 'Работы по благоустройству'
        unique_together = ['block', 'category']
        ordering = ['category__order']

    def __str__(self):
        return f"Блок {self.block.name} / Благ. / {self.category.name}"

    @property
    def progress_pct(self):
        if self.planned_quantity > 0:
            return min(100, round(float(self.fact_quantity / self.planned_quantity * 100), 1))
        return 0


class AsmDocument(models.Model):
    block        = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='asm_documents', verbose_name='Блок'
    )
    floor_number = models.IntegerField('Номер этажа')
    category     = models.ForeignKey(
        'WorkCategory', on_delete=models.CASCADE,
        related_name='asm_documents', verbose_name='Вид работ'
    )
    doc_number   = models.CharField('Номер акта', max_length=50, blank=True)
    doc_date     = models.DateField('Дата акта')
    description  = models.CharField('Описание (зона работ)', max_length=500, blank=True)
    head_warehouse  = models.CharField('Зав. склад',          max_length=200, blank=True)
    head_section    = models.CharField('Нач. участка',        max_length=200, blank=True)
    head_accounting = models.CharField('Главный бухгалтер',   max_length=200, blank=True)
    head_production = models.CharField('Нач. производство',   max_length=200, blank=True)
    created_by   = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_asm_docs', verbose_name='Создал'
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'АСМ'
        verbose_name_plural = 'АСМ — Акты списания материалов'
        ordering = ['-doc_date', '-created_at']

    def __str__(self):
        fn = f'Эт.{self.floor_number}' if self.floor_number >= 0 else f'Подвал {abs(self.floor_number)}'
        return f"АСМ №{self.doc_number} от {self.doc_date} / {fn} / {self.category.name}"

    @property
    def total_amount(self):
        return sum(
            (i.quantity * i.unit_price for i in self.items.all()),
            Decimal('0')
        )


class AsmItem(models.Model):
    document   = models.ForeignKey(
        AsmDocument, on_delete=models.CASCADE,
        related_name='items', verbose_name='Документ'
    )
    order      = models.PositiveIntegerField('Порядок', default=0)
    name       = models.CharField('Наименование материала', max_length=200)
    unit       = models.CharField('Ед. измерения', max_length=30)
    quantity   = models.DecimalField('Количество',  max_digits=12, decimal_places=3, default=0)
    unit_price = models.DecimalField('Цена за ед.', max_digits=12, decimal_places=2, default=0)
    notes      = models.CharField('Примечание', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Строка АСМ'
        verbose_name_plural = 'Строки АСМ'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name

    @property
    def total_amount(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))


class FloorBudget(models.Model):
    block = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='floor_budgets', verbose_name='Блок'
    )
    floor_number   = models.IntegerField('Номер этажа')
    planned_amount = models.DecimalField('Плановый бюджет (сом)', max_digits=15, decimal_places=2, default=0)
    notes          = models.CharField('Примечание', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Бюджет этажа'
        verbose_name_plural = 'Бюджеты этажей'
        unique_together = ['block', 'floor_number']
        ordering = ['floor_number']

    def __str__(self):
        return f"Блок {self.block.name} / Эт.{self.floor_number} / план {self.planned_amount}"


class BlockAccess(models.Model):
    user  = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='block_accesses', verbose_name='Пользователь')
    block = models.ForeignKey('projects.Block', on_delete=models.CASCADE,
                               related_name='user_accesses', verbose_name='Блок')

    class Meta:
        verbose_name = 'Доступ строителя к блоку'
        verbose_name_plural = 'Доступы строителей к блокам'
        unique_together = ['user', 'block']

    def __str__(self):
        return f"{self.user.username} → Блок {self.block.name}"


class FloorCategoryAssignment(models.Model):
    """Какие виды работ назначены на конкретный этаж блока.
    Если для этажа записей нет — по умолчанию все категории активны."""
    block        = models.ForeignKey('projects.Block', on_delete=models.CASCADE,
                                     related_name='floor_category_assignments')
    floor_number = models.IntegerField('Номер этажа')
    category     = models.ForeignKey(WorkCategory, on_delete=models.CASCADE,
                                     related_name='floor_assignments')

    class Meta:
        verbose_name = 'Виды работ по этажу'
        verbose_name_plural = 'Виды работ по этажам'
        unique_together = ['block', 'floor_number', 'category']
        ordering = ['floor_number', 'category__order']

    def __str__(self):
        return f"Блок {self.block.name} / Эт.{self.floor_number} / {self.category.name}"


class AvrDocument(models.Model):
    STATUS_CHOICES = [('draft', 'Черновик'), ('issued', 'Выдан')]
    block        = models.ForeignKey('projects.Block', on_delete=models.CASCADE, related_name='avr_documents', verbose_name='Блок')
    floor_number = models.IntegerField('Номер этажа', null=True, blank=True)
    category     = models.ForeignKey('WorkCategory', on_delete=models.CASCADE, related_name='avr_documents', verbose_name='Вид работ')
    doc_number   = models.CharField('Номер акта', max_length=50, blank=True)
    doc_date     = models.DateField('Дата акта')
    contractor   = models.CharField('Подрядчик ИП', max_length=200, blank=True)
    executor     = models.CharField('Исполнитель', max_length=200, blank=True)
    completion_pct = models.DecimalField('% выполнения', max_digits=5, decimal_places=1, default=100)
    status       = models.CharField('Статус', max_length=10, choices=STATUS_CHOICES, default='draft')
    defects             = models.CharField('Выявленные недостатки', max_length=500, blank=True)
    defect_deadline     = models.CharField('Сроки устранения', max_length=200, blank=True)
    safety_compliance   = models.CharField('Соблюдение ТБ', max_length=200, blank=True)
    deadline_compliance = models.CharField('Выполнение в сроки', max_length=200, blank=True)
    head_production = models.CharField('Начальник производства', max_length=200, blank=True)
    head_section    = models.CharField('Начальник участка', max_length=200, blank=True)
    foreman         = models.CharField('Прораб', max_length=200, blank=True)
    master          = models.CharField('Мастер', max_length=200, blank=True)
    executor_sign   = models.CharField('Исполнитель (подпись)', max_length=200, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_avr_docs')
    created_at = models.DateTimeField(auto_now_add=True)

    is_rework = models.BooleanField('Переделка (не в смете)', default=False)

    # Acceptance fields — set by admin, locks the document
    is_accepted    = models.BooleanField('Принято', default=False)
    accepted_by    = models.CharField('Принял', max_length=200, blank=True)
    accepted_at    = models.DateField('Дата приёмки', null=True, blank=True)
    accepted_amount = models.DecimalField('Сумма к оплате', max_digits=15, decimal_places=2,
                                          null=True, blank=True)

    class Meta:
        verbose_name = 'АВР'
        verbose_name_plural = 'АВР — Акты выполненных работ'
        ordering = ['-doc_date', '-created_at']

    def __str__(self):
        fl = (f'Эт.{self.floor_number}' if self.floor_number and self.floor_number >= 0
              else (f'Подвал {abs(self.floor_number)}' if self.floor_number else 'Общий'))
        return f"АВР №{self.doc_number} от {self.doc_date} / {fl} / {self.category.name}"

    @property
    def total_amount(self):
        return sum((i.quantity * i.unit_price for i in self.items.all()), Decimal('0'))


class AvrPhoto(models.Model):
    document   = models.ForeignKey(AvrDocument, on_delete=models.CASCADE, related_name='photos')
    image      = models.ImageField('Фото', upload_to='avr_photos/')
    caption    = models.CharField('Подпись', max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"Фото к АВР {self.document_id}"


class AvrItem(models.Model):
    document   = models.ForeignKey(AvrDocument, on_delete=models.CASCADE, related_name='items')
    order      = models.PositiveIntegerField('Порядок', default=0)
    name       = models.CharField('Наименование работ', max_length=300)
    unit       = models.CharField('Ед. измерения', max_length=30, blank=True)
    quantity   = models.DecimalField('Кол-во', max_digits=12, decimal_places=3, default=0)
    unit_price = models.DecimalField('Цена', max_digits=12, decimal_places=2, default=0)
    notes      = models.CharField('Примечание', max_length=200, blank=True)

    class Meta:
        ordering = ['order', 'id']

    @property
    def total_amount(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))


class WorkAct(models.Model):
    ACT_TYPES = [
        ('avr', 'АВР — Акт выполненных работ'),
        ('asm', 'АСМ — Акт списанных материалов'),
    ]
    act_type   = models.CharField('Тип акта', max_length=10, choices=ACT_TYPES)
    act_number = models.CharField('Номер акта', max_length=50)
    act_date   = models.DateField('Дата акта')
    block = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='work_acts', verbose_name='Блок'
    )
    contractor = models.CharField('Подрядчик', max_length=200, blank=True)
    floor_works = models.ManyToManyField(
        FloorWork, blank=True, related_name='acts', verbose_name='Работы по этажам'
    )
    landscaping_works = models.ManyToManyField(
        LandscapingWork, blank=True, related_name='acts', verbose_name='Благоустройство'
    )
    total_amount = models.DecimalField('Итого', max_digits=15, decimal_places=2, default=0)
    notes = models.TextField('Примечание', blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_acts', verbose_name='Создал'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Акт'
        verbose_name_plural = 'Акты'
        ordering = ['-act_date', '-created_at']

    def __str__(self):
        return f"{self.get_act_type_display()} №{self.act_number} от {self.act_date}"


class CalendarPlan(models.Model):
    block = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='calendar_plans', verbose_name='Блок'
    )
    name = models.CharField('Название', max_length=200)
    start_year  = models.IntegerField('Год начала')
    start_month = models.IntegerField('Месяц начала')   # 1-12
    end_year    = models.IntegerField('Год окончания')
    end_month   = models.IntegerField('Месяц окончания')  # 1-12
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_calendar_plans', verbose_name='Создал'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Календарный план'
        verbose_name_plural = 'Календарные планы'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (Блок {self.block.name})"

    def month_range(self):
        result = []
        y, m = self.start_year, self.start_month
        while (y, m) <= (self.end_year, self.end_month):
            result.append((y, m))
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return result


class CalendarTask(models.Model):
    plan  = models.ForeignKey(
        CalendarPlan, on_delete=models.CASCADE,
        related_name='tasks', verbose_name='План'
    )
    name  = models.CharField('Наименование', max_length=200)
    unit  = models.CharField('Ед.изм.', max_length=30, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    notes = models.TextField('Примечание', blank=True)

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name


class CalendarMonthPlan(models.Model):
    task           = models.ForeignKey(
        CalendarTask, on_delete=models.CASCADE,
        related_name='month_plans', verbose_name='Задача'
    )
    year           = models.IntegerField('Год')
    month          = models.IntegerField('Месяц')  # 1-12
    planned_amount = models.DecimalField('План сумма', max_digits=15, decimal_places=2, default=0)
    fact_amount    = models.DecimalField('Факт сумма', max_digits=15, decimal_places=2, default=0)
    notes          = models.TextField('Примечание', blank=True)
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='calendar_updates', verbose_name='Обновил'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Помесячный план'
        verbose_name_plural = 'Помесячные планы'
        unique_together = ['task', 'year', 'month']

    def __str__(self):
        return f"{self.task.name} {self.year}/{self.month}"
