from apps.planfact.models import BlockAccess
from .models import CompanyDirector


def user_role(request):
    if not request.user.is_authenticated:
        return {'is_admin_user': False, 'is_builder': False}
    is_admin = request.user.is_staff or request.user.groups.filter(name='Производство').exists()
    is_builder = not is_admin and BlockAccess.objects.filter(user=request.user).exists()
    return {'is_admin_user': is_admin, 'is_builder': is_builder}


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
