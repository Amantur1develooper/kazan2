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
