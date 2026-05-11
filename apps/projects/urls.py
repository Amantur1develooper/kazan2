from django.urls import path
from . import views

urlpatterns = [
    # Organization
    path('orgs/', views.org_list, name='org_list'),
    path('orgs/create/', views.org_create, name='org_create'),
    path('orgs/<int:pk>/', views.org_detail, name='org_detail'),
    path('orgs/<int:pk>/edit/', views.org_update, name='org_update'),
    path('orgs/<int:pk>/delete/', views.org_delete, name='org_delete'),

    # ResidentialComplex
    path('', views.complex_list, name='complex_list'),
    path('create/', views.complex_create, name='complex_create'),
    path('<int:pk>/', views.complex_detail, name='complex_detail'),
    path('<int:pk>/edit/', views.complex_update, name='complex_update'),
    path('<int:pk>/delete/', views.complex_delete, name='complex_delete'),

    # Block
    path('<int:complex_pk>/blocks/create/', views.block_create, name='block_create'),
    path('blocks/<int:pk>/', views.block_detail, name='block_detail'),
    path('blocks/<int:pk>/edit/', views.block_update, name='block_update'),
    path('blocks/<int:pk>/delete/', views.block_delete, name='block_delete'),

    # Stage
    path('blocks/<int:block_pk>/stages/create/', views.stage_create, name='stage_create'),
    path('stages/<int:pk>/', views.stage_detail, name='stage_detail'),
    path('stages/<int:pk>/edit/', views.stage_update, name='stage_update'),
    path('stages/<int:pk>/delete/', views.stage_delete, name='stage_delete'),

    # Floor
    path('stages/<int:stage_pk>/floors/create/', views.floor_create, name='floor_create'),
    path('floors/<int:pk>/', views.floor_detail, name='floor_detail'),
    path('floors/<int:pk>/edit/', views.floor_update, name='floor_update'),
    path('floors/<int:pk>/delete/', views.floor_delete, name='floor_delete'),

    # Floor Expense
    path('floors/<int:floor_pk>/expenses/add/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/edit/', views.expense_update, name='expense_update'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),

    # AJAX
    path('ajax/complexes/', views.ajax_complexes, name='ajax_complexes'),
    path('ajax/blocks/', views.ajax_blocks, name='ajax_blocks'),
    path('ajax/stages/', views.ajax_stages, name='ajax_stages'),
    path('ajax/floors/', views.ajax_floors, name='ajax_floors'),
]
