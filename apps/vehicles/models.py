from decimal import Decimal
from django.db import models


class VehicleTransaction(models.Model):
    """
    Одна операция со складом авто.
    Машина выступает расчётным средством: принята от одного объекта,
    передана подрядчику в зачёт услуг на другом объекте.
    """
    organization = models.ForeignKey(
        'projects.Organization', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='vehicle_transactions',
        verbose_name='Компания'
    )
    date = models.DateField('Дата')
    vehicle_name = models.CharField('Марка / описание авто', max_length=300)

    # Откуда машина
    source_block = models.ForeignKey(
        'projects.Block', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='vehicle_source_transactions',
        verbose_name='Объект поступления (блок)'
    )
    source_text = models.CharField(
        'Объект поступления (текст)', max_length=200, blank=True,
        help_text='Заполняется при импорте если блок не распознан'
    )

    # Финансовая часть
    amount_in  = models.DecimalField('Приход',  max_digits=15, decimal_places=2, default=0)
    amount_out = models.DecimalField('Расход',  max_digits=15, decimal_places=2, default=0)

    # Кому и куда ушло
    counterparty = models.CharField('Подрядчик / кому ушло', max_length=300, blank=True)
    target_block = models.ForeignKey(
        'projects.Block', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='vehicle_target_transactions',
        verbose_name='Объект расхода (блок)'
    )
    target_text = models.CharField('Объект расхода (текст)', max_length=200, blank=True)
    purpose     = models.CharField('За что / куда ушло', max_length=300, blank=True)

    notes       = models.TextField('Примечания', blank=True)
    source_file = models.CharField('Файл-источник', max_length=255, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Операция склада авто'
        verbose_name_plural = 'Операции склада авто'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.date} | {self.vehicle_name[:60]}'

    @property
    def loss(self):
        """Убыток = расход + приход (amount_out обычно отрицателен)."""
        return self.amount_out + self.amount_in

    @property
    def in_balance(self):
        """Машина числится в балансе (ещё не реализована)."""
        return self.amount_out == 0 and self.amount_in <= 0
