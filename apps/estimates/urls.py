from django.urls import path
from . import views

urlpatterns = [
    # Estimates
    path('', views.estimate_list, name='estimate_list'),
    path('<int:pk>/', views.estimate_detail, name='estimate_detail'),
    path('<int:pk>/import/', views.estimate_import, name='estimate_import'),
    path('<int:pk>/versions/<int:version_pk>/', views.estimate_version_detail, name='estimate_version_detail'),
    path('<int:pk>/expense-links/', views.estimate_expense_links, name='estimate_expense_links'),
    path('<int:pk>/unlinked/', views.estimate_unlinked, name='estimate_unlinked'),
    path('<int:pk>/add-misc-sections/', views.estimate_add_misc_sections, name='estimate_add_misc_sections'),
    path('floors/<int:floor_pk>/allocate/', views.floor_allocate_review, name='floor_allocate_review'),

    # Items
    path('sections/<int:section_pk>/items/add/', views.section_item_add, name='section_item_add'),
    path('items/<int:pk>/edit/', views.section_item_edit, name='section_item_edit'),
    path('items/<int:pk>/delete/', views.section_item_delete, name='section_item_delete'),

    # Nomenclature
    path('nomenclature/', views.nomenclature_list, name='nomenclature_list'),
    path('nomenclature/add/', views.nomenclature_create, name='nomenclature_create'),
    path('nomenclature/<int:pk>/edit/', views.nomenclature_edit, name='nomenclature_edit'),
    path('nomenclature/<int:pk>/delete/', views.nomenclature_delete, name='nomenclature_delete'),
]
