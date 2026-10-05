import os
from core.models import HospitalSettings

def hospital_context(request):
    hospital = HospitalSettings.objects.filter(pk=1).first()
    user = getattr(request, "user", None)
    is_pharmacy = bool(user and user.is_authenticated and user.groups.filter(name="Pharmacy").exists())
    return {
        "hospital": hospital,
        "is_pharmacy": is_pharmacy,
        "POSTHOG_KEY": os.getenv("POSTHOG_KEY", ""),
        "POSTHOG_HOST": os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com"),
        "CLOUDFLARE_ANALYTICS_TOKEN": os.getenv("CLOUDFLARE_ANALYTICS_TOKEN", "ab3ab9f60f1b42468eecefb4ff7b00ba"),
    }

