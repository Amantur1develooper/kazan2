from django.contrib import admin
from .models import MainCash, CashTransaction


class CashTransactionInline(admin.TabularInline):
    model = CashTransaction
    extra = 0
    ordering = ['-date']


@admin.register(MainCash)
class MainCashAdmin(admin.ModelAdmin):
    inlines = [CashTransactionInline]
    readonly_fields = ['updated_at']


@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'transaction_type', 'amount', 'description', 'main_cash']
    list_filter = ['transaction_type', 'date']
    search_fields = ['description']
    ordering = ['-date']
