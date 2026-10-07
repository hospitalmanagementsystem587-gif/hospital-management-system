from django.contrib.auth import views as auth_views
from django.urls import include, path

from core import views
from core.portal import views as portal_views


urlpatterns = [
    path("", portal_views.portal_home, name="portal_home"),
    path("", portal_views.portal_home, name="home"),
    path("health/", views.health, name="health"),
    path("accounts/login/", views.HospitalLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("django.contrib.auth.urls")),
]
