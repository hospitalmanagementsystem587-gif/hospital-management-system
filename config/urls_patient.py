from django.urls import include, path


urlpatterns = [path("", include("config.portal_urls"))]
