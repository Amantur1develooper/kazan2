from apps.planfact.models import BlockAccess
from .models import CompanyDirector


def user_role(request):
    if not request.user.is_authenticated:
        return {'is_admin_user': False, 'is_builder': False, 'is_vehicles_only': False, 'is_vehicles_readonly': False}
    is_admin = request.user.is_staff or request.user.groups.filter(name='Производство').exists()
    has_vehicles_write    = not is_admin and request.user.groups.filter(name='Склад авто').exists()
    has_vehicles_readonly = not is_admin and not has_vehicles_write and request.user.groups.filter(name='Склад авто (просмотр)').exists()
    has_vehicles = has_vehicles_write or has_vehicles_readonly
    has_block_access = not is_admin and BlockAccess.objects.filter(user=request.user).exists()
    is_vehicles_only = has_vehicles and not has_block_access
    is_builder = has_block_access
    return {
        'is_admin_user':       is_admin,
        'is_builder':          is_builder,
        'is_vehicles_only':    is_vehicles_only,
        'is_vehicles_readonly': has_vehicles_readonly,
        'has_vehicles':        has_vehicles,
    }


def company_director(request):
    return {'director': CompanyDirector.get()}


def mobile_nav_context(request):
    """Extract block/floor/category from URL kwargs for mobile bottom nav."""
    resolver = request.resolver_match
    if not resolver:
        return {}
    kwargs = resolver.kwargs
    return {
        'current_block_pk': kwargs.get('block_pk'),
        'current_floor_number': kwargs.get('floor_number'),
        'current_category_pk': kwargs.get('category_id'),
    }
