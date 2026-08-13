from django.urls import path
from . import views

urlpatterns = [
    path('',                    views.apartment_list,   name='apartment_list'),
    path('import/',             views.apartment_import, name='apartment_import'),
    path('add/',                views.apartment_create, name='apartment_create'),
    path('<int:pk>/',           views.apartment_detail, name='apartment_detail'),
    path('<int:pk>/edit/',      views.apartment_edit,   name='apartment_edit'),
    path('<int:pk>/delete/',    views.apartment_delete, name='apartment_delete'),
]
