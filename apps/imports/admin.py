from django.contrib import admin
from .models import ExcelImport, ImportLog


class ImportLogInline(admin.TabularInline):
    model = ImportLog
    extra = 0
    readonly_fields = ['log_type', 'row_number', 'message', 'created_at']
    can_delete = False


@admin.register(ExcelImport)
class ExcelImportAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'status', 'rows_processed', 'rows_error', 'uploaded_at']
    list_filter = ['status']
    readonly_fields = ['uploaded_at', 'processed_at', 'rows_total', 'rows_processed', 'rows_error']
    inlines = [ImportLogInline]


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ['excel_import', 'log_type', 'row_number', 'message', 'created_at']
    list_filter = ['log_type']
