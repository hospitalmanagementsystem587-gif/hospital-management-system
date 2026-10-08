import json
import os
from urllib.parse import urljoin

from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

from core.models import HospitalSettings


def hospital_context(request):
    hospital = HospitalSettings.objects.filter(pk=1).first()
    user = getattr(request, "user", None)
    is_pharmacy = bool(user and user.is_authenticated and user.groups.filter(name="Pharmacy").exists())
    portal = getattr(request, "portal", None)
    public_home = bool(
        not portal
        and not (user and user.is_authenticated)
        and getattr(getattr(request, "resolver_match", None), "url_name", None) == "home"
    )

    hospital_name = (
        hospital.name
        if hospital and hospital.name and hospital.name != "Hospital name not configured"
        else "Vedant Hospital"
    )
    public_site_url = settings.PUBLIC_SITE_URL
    canonical_url = f"{public_site_url}/" if public_home else ""
    og_image_url = urljoin(f"{public_site_url}/", static(settings.DEFAULT_OG_IMAGE_PATH))
    schema = {
        "@context": "https://schema.org",
        "@type": "Hospital",
        "name": hospital_name,
        "url": f"{public_site_url}/",
        "image": og_image_url,
    }
    if hospital:
        if hospital.phone:
            schema["telephone"] = hospital.phone
        if hospital.email:
            schema["email"] = hospital.email
        address_parts = [hospital.address, hospital.city]
        if any(address_parts):
            schema["address"] = {
                "@type": "PostalAddress",
                "streetAddress": hospital.address,
                "addressLocality": hospital.city,
                "addressCountry": "IN",
            }
    schema_json = (
        json.dumps(schema, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

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
        "seo_is_indexable": public_home,
        "seo_canonical_url": canonical_url,
        "seo_title": f"{hospital_name} | Hospital Care in Lucknow",
        "seo_description": (
            f"Learn about {hospital_name} and access its secure hospital services workspace "
            "for appointments, clinical care, pharmacy and billing operations."
        ),
        "seo_og_image_url": og_image_url,
        "seo_schema_json": mark_safe(schema_json),
        "GOOGLE_SITE_VERIFICATION": settings.GOOGLE_SITE_VERIFICATION,
    }
