from functools import wraps
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect


def editor_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, 'У вас нет прав для выполнения этого действия.')
            return redirect(request.META.get('HTTP_REFERER', '/'))
        return view_func(request, *args, **kwargs)
    return wrapper


def _is_admin(user):
    return user.is_staff or user.groups.filter(name='Производство').exists()

def _has_vehicles_any(user):
    return user.groups.filter(name__in=['Склад авто', 'Склад авто (просмотр)']).exists()

def _has_vehicles_write(user):
    return user.groups.filter(name='Склад авто').exists()


def vehicles_access_required(view_func):
    """Allow admins, 'Склад авто' and 'Склад авто (просмотр)' members."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not _is_admin(user) and not _has_vehicles_any(user):
            messages.error(request, 'У вас нет доступа к разделу «Склад авто».')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def vehicles_write_required(view_func):
    """Allow only admins and 'Склад авто' (full access) members."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not _is_admin(user) and not _has_vehicles_write(user):
            messages.error(request, 'У вас нет прав на изменение данных в «Склад авто».')
            return redirect('vehicle_list')
        return view_func(request, *args, **kwargs)
    return wrapper


def non_vehicles_required(view_func):
    """Block vehicles-only users from accessing other parts of the system."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not _is_admin(user) and _has_vehicles_any(user) and not _has_vehicles_write(user):
            return redirect('vehicle_list')
        if not _is_admin(user) and _has_vehicles_write(user):
            return redirect('vehicle_list')
        return view_func(request, *args, **kwargs)
    return wrapper
