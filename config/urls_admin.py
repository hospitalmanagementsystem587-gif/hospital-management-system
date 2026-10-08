from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path

urlpatterns = [
    path("", lambda request: redirect("admin:index")),
    path("admin/", admin.site.urls),
    path("", include("config.portal_urls")),
]


def admin_permission_denied(request, exception=None):
    """Render a permission response without depending on staff-portal routes."""
    return render(request, "admin/403.html", status=403)


handler403 = admin_permission_denied
