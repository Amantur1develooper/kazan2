from django.contrib import admin
from .models import CashAccount, DDSImport, CashFlowRecord


@admin.register(CashAccount)
class CashAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'account_type', 'residential_complex']
    list_filter = ['account_type', 'residential_complex']


@admin.register(DDSImport)
class DDSImportAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'residential_complex', 'status', 'rows_processed', 'uploaded_at']
    list_filter = ['status', 'residential_complex']


@admin.register(CashFlowRecord)
class CashFlowRecordAdmin(admin.ModelAdmin):
    list_display = ['operation_date', 'operation_type', 'direction', 'amount', 'account', 'block']
    list_filter = ['direction', 'block', 'account']
    search_fields = ['operation_type', 'counterparty', 'object_ref', 'description']
