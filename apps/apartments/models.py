from decimal import Decimal
from django.db import models


class Apartment(models.Model):
    STATUS_FREE     = 'free'
    STATUS_RESERVED = 'reserved'
    STATUS_SOLD     = 'sold'
    STATUS_BARTER   = 'barter'

    block = models.ForeignKey(
        'projects.Block', on_delete=models.CASCADE,
        related_name='apartments', verbose_name='Блок'
    )
    floor = models.IntegerField('Этаж', default=1)
    apartment_number = models.CharField('Номер квартиры', max_length=100)
    rooms = models.IntegerField('Количество комнат', default=1)
    area = models.DecimalField('Площадь (м²)', max_digits=10, decimal_places=2)

    # Pricing
    planned_price_per_m2 = models.DecimalField(
        'Плановая цена м²', max_digits=12, decimal_places=2, default=0
    )
    fact_price_per_m2 = models.DecimalField(
        'Фактическая цена м²', max_digits=12, decimal_places=2, default=0
    )

    # Deal
    client_name = models.CharField('ФИО клиента', max_length=300, blank=True)
    phone = models.CharField('Телефон', max_length=50, blank=True)
    deal_date = models.DateField('Дата договора', null=True, blank=True)
    deal_number = models.CharField('Номер договора', max_length=100, blank=True)
    deal_amount_contract = models.DecimalField(
        'Сумма договора', max_digits=15, decimal_places=2, default=0
    )
    deal_amount_paid = models.DecimalField(
        'Оплачено', max_digits=15, decimal_places=2, default=0
    )
    deal_amount_remaining = models.DecimalField(
        'Остаток к оплате', max_digits=15, decimal_places=2, default=0
    )
    discount = models.DecimalField('Скидка', max_digits=15, decimal_places=2, default=0)

    # Status flags
    is_sold = models.BooleanField('Продана', default=False)
    is_reserved = models.BooleanField('Бронь', default=False)
    is_barter = models.BooleanField('Бартер', default=False)

    # Aux
    contract_type = models.CharField('Тип сделки', max_length=100, blank=True)
    curator = models.CharField('Куратор', max_length=100, blank=True)
    notes = models.TextField('Примечания', blank=True)
    source_file = models.CharField('Файл-источник', max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Квартира'
        verbose_name_plural = 'Квартиры'
        unique_together = ['block', 'apartment_number']
        ordering = ['floor', 'apartment_number']

    def __str__(self):
        return f'{self.block} / кв. {self.apartment_number}'

    @property
    def status(self):
        if self.is_barter:
            return self.STATUS_BARTER
        if self.is_sold:
            return self.STATUS_SOLD
        if self.is_reserved:
            return self.STATUS_RESERVED
        return self.STATUS_FREE

    @property
    def status_display(self):
        return {
            self.STATUS_FREE:     'Свободна',
            self.STATUS_RESERVED: 'Бронь',
            self.STATUS_SOLD:     'Продана',
            self.STATUS_BARTER:   'Бартер',
        }[self.status]

    @property
    def status_color(self):
        return {
            self.STATUS_FREE:     'success',
            self.STATUS_RESERVED: 'warning',
            self.STATUS_SOLD:     'primary',
            self.STATUS_BARTER:   'secondary',
        }[self.status]

    @property
    def planned_deal_amount(self):
        if self.is_sold:
            return Decimal('0')
        return (self.area * self.planned_price_per_m2).quantize(Decimal('0.01'))
