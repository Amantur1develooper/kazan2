from django.contrib import admin
from .models import WorkCategory, BlockFloorConfig, FloorWork, LandscapingWork, WorkAct, CalendarPlan, CalendarTask, CalendarMonthPlan


@admin.register(WorkCategory)
class WorkCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'unit', 'scope', 'color', 'order']
    list_editable = ['order', 'scope', 'color']
    ordering = ['order']


@admin.register(BlockFloorConfig)
class BlockFloorConfigAdmin(admin.ModelAdmin):
    list_display = ['block', 'total_floors', 'underground_floors', 'has_landscaping']


@admin.register(FloorWork)
class FloorWorkAdmin(admin.ModelAdmin):
    list_display = ['block', 'floor_number', 'category', 'planned_quantity', 'fact_quantity', 'fact_date']
    list_filter = ['block', 'category']


@admin.register(LandscapingWork)
class LandscapingWorkAdmin(admin.ModelAdmin):
    list_display = ['block', 'category', 'planned_quantity', 'fact_quantity']
    list_filter = ['block', 'category']


@admin.register(WorkAct)
class WorkActAdmin(admin.ModelAdmin):
    list_display = ['act_number', 'act_type', 'act_date', 'block', 'contractor', 'total_amount']
    list_filter = ['act_type', 'block']
    filter_horizontal = ['floor_works', 'landscaping_works']


@admin.register(CalendarPlan)
class CalendarPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'block', 'start_year', 'start_month', 'end_year', 'end_month', 'created_at']
    list_filter = ['block']


@admin.register(CalendarTask)
class CalendarTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan', 'unit', 'order']
    list_filter = ['plan']


@admin.register(CalendarMonthPlan)
class CalendarMonthPlanAdmin(admin.ModelAdmin):
    list_display = ['task', 'year', 'month', 'planned_amount', 'fact_amount']
    list_filter = ['year', 'month']
