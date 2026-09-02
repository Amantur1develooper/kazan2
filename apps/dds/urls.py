from django.urls import path
from . import views

urlpatterns = [
    path('import/', views.dds_import_upload, name='dds_import_upload'),
    path('import/planfact/', views.dds_planfact_upload, name='dds_planfact_upload'),
    path('import/<int:pk>/preview/', views.dds_import_preview, name='dds_import_preview'),
    path('import/<int:pk>/distribute/', views.dds_distribute, name='dds_distribute'),
    path('accounts/', views.dds_account_list, name='dds_account_list'),
    path('accounts/<int:pk>/', views.dds_account_detail, name='dds_account_detail'),
    path('accounts/<int:pk>/edit/', views.dds_account_edit, name='dds_account_edit'),
    path('accounts/<int:pk>/add/', views.dds_record_create, name='dds_record_create'),
    path('records/<int:pk>/edit/', views.dds_record_edit, name='dds_record_edit'),
    path('records/<int:pk>/delete/', views.dds_record_delete, name='dds_record_delete'),
    path('unlinked/', views.dds_unlinked, name='dds_unlinked'),
]
