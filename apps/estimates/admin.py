from django.contrib import admin
from .models import NomenclatureGroup, Nomenclature, NomenclatureAlias, Estimate, EstimateSection, EstimateItem


@admin.register(NomenclatureGroup)
class NomenclatureGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'order']
    ordering = ['order', 'name']


@admin.register(Nomenclature)
class NomenclatureAdmin(admin.ModelAdmin):
    list_display = ['name', 'code_1c', 'unit', 'group', 'is_active']
    list_filter = ['group', 'is_active']
    search_fields = ['name', 'code_1c']


@admin.register(NomenclatureAlias)
class NomenclatureAliasAdmin(admin.ModelAdmin):
    list_display = ['alias_name', 'nomenclature']
    search_fields = ['alias_name']


class EstimateSectionInline(admin.TabularInline):
    model = EstimateSection
    extra = 0
    fields = ['code', 'name', 'order', 'total_amount']


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    list_display = ['block', 'status', 'total_amount', 'updated_at']
    list_filter = ['status']
    inlines = [EstimateSectionInline]


@admin.register(EstimateSection)
class EstimateSectionAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'estimate', 'parent', 'total_amount']
    list_filter = ['estimate']
    search_fields = ['name', 'code']


@admin.register(EstimateItem)
class EstimateItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'section', 'nomenclature', 'quantity', 'unit_price', 'total_amount']
    list_filter = ['section__estimate']
    search_fields = ['name']
