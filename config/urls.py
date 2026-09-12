from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from apps.core.views import SmartLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', SmartLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('apps.core.urls')),
    path('complexes/', include('apps.projects.urls')),
    path('imports/', include('apps.imports.urls')),
    path('estimates/', include('apps.estimates.urls')),
    path('dds/', include('apps.dds.urls')),
    path('vehicles/', include('apps.vehicles.urls')),
    path('apartments/', include('apps.apartments.urls')),
    path('analytics/', include('apps.projects.analytics_urls')),
    path('planfact/', include('apps.planfact.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
