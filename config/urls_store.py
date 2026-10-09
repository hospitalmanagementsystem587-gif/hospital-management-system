from django.urls import include, path

from config.urls import urlpatterns as legacy_urlpatterns
from core import views

urlpatterns = [
    path("", views.pharmacy_dashboard, name="pharmacy_dashboard"),
    path("", include("config.portal_urls")),
]
urlpatterns += legacy_urlpatterns
