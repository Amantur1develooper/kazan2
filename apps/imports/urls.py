from django.urls import path
from . import views

urlpatterns = [
    path('', views.import_list, name='import_list'),
    path('upload/', views.import_upload, name='import_upload'),
    path('<int:pk>/preview/', views.import_preview, name='import_preview'),
    path('<int:pk>/', views.import_detail, name='import_detail'),
    path('<int:pk>/reprocess/', views.import_reprocess, name='import_reprocess'),
]
