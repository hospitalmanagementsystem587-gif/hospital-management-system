import os
from core.models import HospitalSettings

def hospital_context(request):
    hospital = HospitalSettings.objects.filter(pk=1).first()
    user = getattr(request, "user", None)
    is_pharmacy = bool(user and user.is_authenticated and user.groups.filter(name="Pharmacy").exists())
    portal = getattr(request, "portal", None)

    # Portal title and brand URL resolution
    portal_titles = {
        "admin": "Hospital Management & CMS",
        "staff": "Clinical Operations",
        "store": "Pharmacy & Store",
        "patient": "Patient Portal",
        "agent": "Hospital Support",
    }
    portal_title = portal_titles.get(portal, "Hospital Management System")

    # Portal brand link (safe reverse with fallback)
    portal_brand_url = "/"
    if portal == "admin":
        portal_brand_url = "/admin/"
    elif portal == "staff":
        portal_brand_url = "/"

    # User role label in portal shell
    user_role_label = "Authorized staff"
    if user and user.is_authenticated:
        if user.is_superuser:
            user_role_label = "System Administrator"
        elif user.groups.filter(name="Doctor").exists():
            user_role_label = "Attending Doctor"
        elif user.groups.filter(name="Reception").exists():
            user_role_label = "Front Desk & Reception"
        elif user.groups.filter(name="Pharmacy").exists():
            user_role_label = "Pharmacy Staff"
        elif hasattr(user, "patient_account") and user.patient_account.is_verified:
            user_role_label = "Verified Patient"
        elif user.is_staff:
            user_role_label = "Hospital Staff"

    return {
        "hospital": hospital,
        "is_pharmacy": is_pharmacy,
        "portal": portal,
        "portal_title": portal_title,
        "portal_brand_url": portal_brand_url,
        "user_role_label": user_role_label,
        "POSTHOG_KEY": os.getenv("POSTHOG_KEY", ""),
        "POSTHOG_HOST": os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com"),
        "CLOUDFLARE_ANALYTICS_TOKEN": os.getenv("CLOUDFLARE_ANALYTICS_TOKEN", "ab3ab9f60f1b42468eecefb4ff7b00ba"),
    }

