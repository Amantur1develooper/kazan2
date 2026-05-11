from django.db import models


class ExcelImport(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает обработки'),
        ('processing', 'Обрабатывается'),
        ('completed', 'Завершён'),
        ('error', 'Ошибка'),
    ]

    file = models.FileField('Файл', upload_to='imports/%Y/%m/')
    original_filename = models.CharField('Имя файла', max_length=255)

    # Target: when importing into a specific floor
    target_floor = models.ForeignKey(
        'projects.Floor', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='imports', verbose_name='Целевой этаж'
    )

    # Import mode
    IMPORT_MODES = [
        ('replace', 'Заменить существующие'),
        ('add', 'Суммировать с существующими'),
    ]
    import_mode = models.CharField('Режим импорта', max_length=10,
                                    choices=IMPORT_MODES, default='replace')

    uploaded_at = models.DateTimeField('Загружен', auto_now_add=True)
    processed_at = models.DateTimeField('Обработан', null=True, blank=True)
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='pending')

    # Column mapping stored as JSON: {"complex": 0, "block": 1, "stage": 2, ...}
    column_mapping = models.JSONField('Маппинг столбцов', default=dict, blank=True)

    rows_total = models.IntegerField('Всего строк', default=0)
    rows_processed = models.IntegerField('Обработано', default=0)
    rows_error = models.IntegerField('Ошибок', default=0)
    error_message = models.TextField('Сообщение об ошибке', blank=True)
    notes = models.TextField('Заметки', blank=True)

    class Meta:
        verbose_name = 'Импорт Excel'
        verbose_name_plural = 'Импорты Excel'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at:%d.%m.%Y %H:%M})"

    def get_status_color(self):
        colors = {
            'pending': 'secondary',
            'processing': 'primary',
            'completed': 'success',
            'error': 'danger',
        }
        return colors.get(self.status, 'secondary')


class ImportLog(models.Model):
    LOG_TYPES = [
        ('info', 'Инфо'),
        ('success', 'Успех'),
        ('warning', 'Предупреждение'),
        ('error', 'Ошибка'),
    ]

    excel_import = models.ForeignKey(
        ExcelImport, on_delete=models.CASCADE,
        related_name='logs', verbose_name='Импорт'
    )
    log_type = models.CharField('Тип', max_length=10, choices=LOG_TYPES, default='info')
    row_number = models.IntegerField('Номер строки', null=True, blank=True)
    message = models.TextField('Сообщение')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Лог импорта'
        verbose_name_plural = 'Логи импорта'
        ordering = ['created_at']

    def get_log_color(self):
        colors = {
            'info': 'primary',
            'success': 'success',
            'warning': 'warning',
            'error': 'danger',
        }
        return colors.get(self.log_type, 'secondary')
