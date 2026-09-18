from django.contrib import admin
from django.utils.html import format_html
from .models import MainCash, CashTransaction, CompanyDirector


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


@admin.register(CompanyDirector)
class CompanyDirectorAdmin(admin.ModelAdmin):
    fields = ['photo', 'photo_preview', 'name', 'position', 'company', 'phone', 'email', 'bio']
    readonly_fields = ['photo_preview']

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="width:120px;height:120px;object-fit:cover;'
                'border-radius:50%;border:3px solid #e2e8f0;margin-top:6px">',
                obj.photo.url
            )
        return '—'
    photo_preview.short_description = 'Предпросмотр'

    def has_add_permission(self, request):
        return not CompanyDirector.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
