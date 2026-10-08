import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG", default=False)
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set DJANGO_SECRET_KEY before running with DEBUG disabled.")
    SECRET_KEY = "django-insecure-local-development-only"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(
        ","
    )
    if host.strip()
]
if "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

# KAN-35: every portal is a host-based view over this Django application and
# its single configured database. Production must set each host explicitly.
PORTAL_HOSTS = {
    "admin": os.getenv("HMS_ADMIN_HOST", "admin.localhost"),
    "staff": os.getenv("HMS_STAFF_HOST", "staff.localhost"),
    "store": os.getenv("HMS_STORE_HOST", "store.localhost"),
    "patient": os.getenv("HMS_PATIENT_HOST", "patient.localhost"),
    "agent": os.getenv("HMS_AGENT_HOST", "agent.localhost"),
}
if DEBUG and ".localhost" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".localhost")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "https://*.onrender.com,https://*.pages.dev,https://*.workers.dev",
    ).split(",")
    if origin.strip()
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Public-origin SEO and transport policy. PUBLIC_SITE_URL is deliberately
# configured rather than derived from Host headers so canonical and social URLs
# cannot be poisoned by an inbound request.
PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", "http://testserver").rstrip("/")
if not urlsplit(PUBLIC_SITE_URL).scheme or not urlsplit(PUBLIC_SITE_URL).netloc:
    raise RuntimeError("PUBLIC_SITE_URL must be an absolute URL, for example https://example.com")
GOOGLE_SITE_VERIFICATION = os.getenv("GOOGLE_SITE_VERIFICATION", "").strip()
DEFAULT_OG_IMAGE_PATH = "core/stitch_preview.png"

INSTALLED_APPS = [
    "core",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.seo.NoIndexPrivateResponsesMiddleware",
    "core.portal.middleware.PortalRoutingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.hospital_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///db.sqlite3",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_PATIENT_DOCUMENT_ROOT = Path(
    os.getenv(
        "PRIVATE_PATIENT_DOCUMENT_ROOT",
        BASE_DIR / "private-media" / "patient-documents",
    )
)
PATIENT_DOCUMENT_MAX_BYTES = int(
    os.getenv("PATIENT_DOCUMENT_MAX_BYTES", str(10 * 1024 * 1024))
)
PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK = os.getenv(
    "PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK", ""
).strip()
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Session cookie domain policy:
# Explicitly configured via DJANGO_SESSION_COOKIE_DOMAIN (e.g. '.example.com' for shared cross-subdomain
# sessions across admin/staff/store/patient/agent, or None for strict host-only cookie isolation).
SESSION_COOKIE_DOMAIN = os.getenv("DJANGO_SESSION_COOKIE_DOMAIN", None) or None
CSRF_COOKIE_DOMAIN = os.getenv("DJANGO_CSRF_COOKIE_DOMAIN", None) or None

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = int(os.getenv("DJANGO_SESSION_COOKIE_AGE", "28800"))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_PASSWORD", os.getenv("RESEND_KEY", ""))

if EMAIL_HOST_PASSWORD and RESEND_FROM_EMAIL:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "smtp.resend.com")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_USER", "resend")
EMAIL_USE_SSL = env_bool("DJANGO_EMAIL_USE_SSL", default=not DEBUG)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = RESEND_FROM_EMAIL or "webmaster@localhost"

SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
        environment=os.getenv("APP_ENV", "staging" if not DEBUG else "development"),
    )

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "300/minute",
        "auth_anon": "10/minute",
        "appointment_write": "20/minute",
    },
    "EXCEPTION_HANDLER": "core.api.exceptions.custom_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
