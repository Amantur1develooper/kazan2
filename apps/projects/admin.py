from django.contrib import admin
from .models import Organization, ResidentialComplex, Block, Stage, Floor, FloorExpense


class ComplexInline(admin.TabularInline):
    model = ResidentialComplex
    extra = 0
    fields = ['name', 'status', 'total_planned_cost']
    show_change_link = True


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'complexes_count']
    inlines = [ComplexInline]

    def complexes_count(self, obj): return obj.complexes.count()
    complexes_count.short_description = 'ЖК'


class BlockInline(admin.TabularInline):
    model = Block
    extra = 0
    show_change_link = True


@admin.register(ResidentialComplex)
class ResidentialComplexAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'status', 'total_planned_cost']
    list_filter = ['status', 'organization']
    search_fields = ['name']
    inlines = [BlockInline]


class StageInline(admin.TabularInline):
    model = Stage
    extra = 0
    show_change_link = True


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ['name', 'residential_complex', 'total_budget']
    list_filter = ['residential_complex']
    search_fields = ['name']
    inlines = [StageInline]


class FloorInline(admin.TabularInline):
    model = Floor
    extra = 0
    show_change_link = True


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ['name', 'block', 'planned_expenses', 'actual_expenses', 'order']
    list_filter = ['block__residential_complex']
    search_fields = ['name']
    inlines = [FloorInline]


class ExpenseInline(admin.TabularInline):
    model = FloorExpense
    extra = 0
    fields = ['item_code', 'name', 'unit', 'quantity', 'unit_price', 'total_amount']


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'number', 'expenses_count']
    list_filter = ['stage__block__residential_complex']
    inlines = [ExpenseInline]

    def expenses_count(self, obj): return obj.expenses.count()
    expenses_count.short_description = 'Расходов'


@admin.register(FloorExpense)
class FloorExpenseAdmin(admin.ModelAdmin):
    list_display = ['name', 'floor', 'quantity', 'unit_price', 'total_amount']
    list_filter = ['floor__stage__block__residential_complex']
    search_fields = ['name', 'item_code']
