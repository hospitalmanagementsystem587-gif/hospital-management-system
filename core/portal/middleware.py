from dataclasses import dataclass

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import set_urlconf


@dataclass(frozen=True)
class PortalDefinition:
    urlconf: str
    groups: frozenset[str]
    patient_only: bool = False


PORTALS = {
    "admin": PortalDefinition("config.urls_admin", frozenset()),
    "staff": PortalDefinition(
        "config.urls_staff",
        frozenset({"Administrator", "Doctor", "Reception", "Pharmacy"}),
    ),
    "store": PortalDefinition(
        "config.urls_store", frozenset({"Administrator", "Pharmacy"})
    ),
    "patient": PortalDefinition(
        "config.urls_patient", frozenset(), patient_only=True
    ),
    # There is no support-agent role in the current authorization model. Keep
    # this future portal administrator-only until its dedicated role ticket.
    "agent": PortalDefinition("config.urls_agent", frozenset({"Administrator"})),
}


def portal_for_host(host):
    normalized_host = host.partition(":")[0].rstrip(".").lower()
    for portal, configured_host in settings.PORTAL_HOSTS.items():
        normalized_configured_host = (
            configured_host.partition(":")[0].rstrip(".").lower()
        )
        if normalized_host == normalized_configured_host:
            return portal
    return None


def user_can_access_portal(user, portal):
    if user.is_superuser:
        return True

    definition = PORTALS[portal]
    if portal == "admin":
        # Django admin independently requires is_staff; enforce the same gate
        # at the host boundary instead of implying that group membership alone
        # grants CMS access.
        return user.is_staff

    if definition.patient_only:
        account = getattr(user, "patient_account", None)
        return bool(
            account
            and account.is_verified
            and account.patient.archived_at is None
        )

    return user.groups.filter(name__in=definition.groups).exists()


class PortalRoutingMiddleware:
    """Select a portal URLconf and enforce its coarse server-side boundary."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        portal = portal_for_host(request.get_host())
        request.portal = portal

        # The existing Android API contract remains independent of browser
        # portals and continues to use its existing JWT permission classes.
        if portal is None or request.path_info.startswith("/api/v1/"):
            return self.get_response(request)

        request.urlconf = PORTALS[portal].urlconf
        set_urlconf(request.urlconf)
        try:
            if self._is_public_portal_path(request.path_info):
                return self.get_response(request)
            if not request.user.is_authenticated:
                return redirect(f"/accounts/login/?next={request.get_full_path()}")
            if not user_can_access_portal(request.user, portal):
                return HttpResponseForbidden("This account cannot access this portal.")
            return self.get_response(request)
        finally:
            set_urlconf(None)

    @staticmethod
    def _is_public_portal_path(path):
        static_url = settings.STATIC_URL
        static_path = static_url if static_url.startswith("/") else f"/{static_url}"
        return (
            path == "/health/"
            or path.startswith("/accounts/")
            or path.startswith(static_path)
        )
