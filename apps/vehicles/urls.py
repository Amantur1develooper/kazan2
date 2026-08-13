from django.urls import path
from . import views

urlpatterns = [
    path('',              views.vehicle_list,   name='vehicle_list'),
    path('import/',       views.vehicle_import, name='vehicle_import'),
    path('add/',          views.vehicle_create, name='vehicle_create'),
    path('<int:pk>/edit/',   views.vehicle_edit,   name='vehicle_edit'),
    path('<int:pk>/delete/', views.vehicle_delete, name='vehicle_delete'),
]
