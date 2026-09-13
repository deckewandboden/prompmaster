from django.db import OperationalError, ProgrammingError


def navigation(request):
    membership = None
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        try:
            from apps.companies.models import Membership
            membership = (
                Membership.objects.filter(user=user, active=True)
                .select_related("company")
                .first()
            )
        except (OperationalError, ProgrammingError):
            # During first migrations the companies table may not exist yet.
            # Programming defects must not be hidden by a broad Exception.
            membership = None
    return {"pm_environment": "PromptMaster", "current_membership": membership}
