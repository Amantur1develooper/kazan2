from django.urls import path
from . import analytics_views

urlpatterns = [
    path('', analytics_views.analytics_index, name='analytics_index'),
    path('<int:pk>/', analytics_views.rc_analytics, name='rc_analytics'),
]
