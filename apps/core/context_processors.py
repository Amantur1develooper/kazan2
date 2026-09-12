from apps.planfact.models import BlockAccess


def user_role(request):
    if not request.user.is_authenticated:
        return {'is_admin_user': False, 'is_builder': False}
    is_admin = request.user.is_staff or request.user.groups.filter(name='Производство').exists()
    is_builder = not is_admin and BlockAccess.objects.filter(user=request.user).exists()
    return {'is_admin_user': is_admin, 'is_builder': is_builder}
