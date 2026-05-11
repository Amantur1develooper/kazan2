from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('cash/', views.cash_detail, name='cash_detail'),
    path('cash/transactions/add/', views.transaction_create, name='transaction_create'),
    path('cash/transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),
]
