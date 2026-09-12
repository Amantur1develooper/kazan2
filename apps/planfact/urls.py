from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.planfact_index, name='planfact_index'),
    path('<int:block_pk>/', views.planfact_block, name='planfact_block'),
    re_path(r'^(?P<block_pk>[0-9]+)/floor/(?P<floor_number>-?[0-9]+)/$', views.planfact_floor_edit, name='planfact_floor_edit'),
    path('<int:block_pk>/landscaping/', views.planfact_landscaping_edit, name='planfact_landscaping_edit'),
    path('<int:block_pk>/floor-budget/', views.floor_budget_edit, name='floor_budget_edit'),
    # ASM
    re_path(r'^(?P<block_pk>[0-9]+)/floor/(?P<floor_number>-?[0-9]+)/cat/(?P<category_id>[0-9]+)/asm/$',
            views.asm_list, name='asm_list'),
    re_path(r'^(?P<block_pk>[0-9]+)/floor/(?P<floor_number>-?[0-9]+)/cat/(?P<category_id>[0-9]+)/asm/create/$',
            views.asm_create, name='asm_create'),
    path('asm/<int:asm_pk>/', views.asm_edit,   name='asm_edit'),
    path('asm/<int:asm_pk>/print/', views.asm_print, name='asm_print'),
    path('asm/<int:asm_pk>/delete/', views.asm_delete, name='asm_delete'),
    # AVR
    re_path(r'^(?P<block_pk>[0-9]+)/floor/(?P<floor_number>-?[0-9]+)/cat/(?P<category_id>[0-9]+)/avr/$',
            views.avr_list, name='avr_list'),
    re_path(r'^(?P<block_pk>[0-9]+)/floor/(?P<floor_number>-?[0-9]+)/cat/(?P<category_id>[0-9]+)/avr/create/$',
            views.avr_create, name='avr_create'),
    path('avr/<int:avr_pk>/', views.avr_edit, name='avr_edit'),
    path('avr/<int:avr_pk>/print/', views.avr_print, name='avr_print'),
    path('avr/<int:avr_pk>/delete/', views.avr_delete, name='avr_delete'),
    path('<int:block_pk>/act/create/', views.act_create, name='act_create'),
    path('<int:block_pk>/acts/', views.act_list, name='act_list'),
    path('act/<int:pk>/print/', views.act_print, name='act_print'),
    # Calendar plan
    path('<int:block_pk>/calendar/', views.calendar_plan_list, name='calendar_plan_list'),
    path('<int:block_pk>/calendar/create/', views.calendar_plan_create, name='calendar_plan_create'),
    path('calendar/<int:plan_pk>/', views.calendar_plan_detail, name='calendar_plan_detail'),
    path('calendar/<int:plan_pk>/tasks/', views.calendar_task_edit, name='calendar_task_edit'),
    path('calendar/<int:plan_pk>/fact/', views.calendar_fact_enter, name='calendar_fact_enter'),
    path('calendar/<int:plan_pk>/delete/', views.calendar_plan_delete, name='calendar_plan_delete'),
    path('<int:block_pk>/progress/', views.progress_board, name='progress_board'),
    path('<int:block_pk>/progress/excel/', views.progress_board_excel, name='progress_board_excel'),
    path('<int:block_pk>/floor-categories/', views.floor_category_edit, name='floor_category_edit'),
    # Builder user management
    path('users/', views.manage_users, name='manage_users'),
    path('users/create/', views.manage_user_create, name='manage_user_create'),
    path('users/<int:user_pk>/edit/', views.manage_user_edit, name='manage_user_edit'),
]
