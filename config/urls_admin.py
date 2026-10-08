from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from config.urls import urlpatterns as legacy_urlpatterns

urlpatterns = [
    path("", lambda request: redirect("admin:index")),
    path("admin/", admin.site.urls),
    path("", include("config.portal_urls")),
]
urlpatterns += legacy_urlpatterns
