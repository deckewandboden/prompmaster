from functools import wraps
from django.core.exceptions import PermissionDenied
from apps.accounts.models import UserRole

def has_perm(user,code):
    if not user.is_authenticated: return False
    if user.is_superuser: return True
    return UserRole.objects.filter(user=user,role__active=True,role__permissions__code=code).exists()
def permission_required(code):
    def deco(fn):
        @wraps(fn)
        def inner(request,*a,**kw):
            if not has_perm(request.user,code): raise PermissionDenied
            return fn(request,*a,**kw)
        return inner
    return deco
