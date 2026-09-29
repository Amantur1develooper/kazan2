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


def vehicles_access_required(view_func):
    """Allow only admins and 'Склад авто' group members."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        is_admin = user.is_staff or user.groups.filter(name='Производство').exists()
        is_vehicles = user.groups.filter(name='Склад авто').exists()
        if not is_admin and not is_vehicles:
            messages.error(request, 'У вас нет доступа к разделу «Склад авто».')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def non_vehicles_required(view_func):
    """Block 'Склад авто'-only users from accessing other parts of the system."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        is_admin = user.is_staff or user.groups.filter(name='Производство').exists()
        if not is_admin and user.groups.filter(name='Склад авто').exists():
            return redirect('vehicle_list')
        return view_func(request, *args, **kwargs)
    return wrapper
