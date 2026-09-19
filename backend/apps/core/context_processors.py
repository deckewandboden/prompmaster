from django.db import OperationalError, ProgrammingError


def navigation(request):
    membership = None
    can_start_pro = False
    internal_staff = False
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        try:
            from apps.companies.models import Membership
            membership = (
                Membership.objects.filter(user=user, active=True)
                .select_related("company")
                .first()
            )
            from apps.proaccess.services import active_product_assignment, has_internal_staff_access
            internal_staff = has_internal_staff_access(user)
            can_start_pro = internal_staff or bool(active_product_assignment(user, 'PRO'))
        except (OperationalError, ProgrammingError):
            # During first migrations the companies table may not exist yet.
            # Programming defects must not be hidden by a broad Exception.
            membership = None
            can_start_pro = bool(getattr(user, 'is_staff', False) and getattr(user, 'is_active', False))
            internal_staff = can_start_pro
    return {
        "pm_environment": "PromptMaster",
        "current_membership": membership,
        "pm_can_start_pro": can_start_pro,
        "pm_internal_staff": internal_staff,
    }
