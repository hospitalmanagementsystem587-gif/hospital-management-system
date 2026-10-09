from django.shortcuts import render
from django.urls import include, path

from config.urls import urlpatterns as legacy_urlpatterns
from core import views

urlpatterns = [
    path("", views.agent_ticket_queue, name="agent_ticket_queue"),
    path("tickets/<int:pk>/", views.agent_ticket_workspace, name="agent_ticket_workspace"),
    path("", include("config.portal_urls")),
]
urlpatterns += legacy_urlpatterns


def agent_permission_denied(request, exception=None):
    return render(request, "403.html", {"exception": str(exception)}, status=403)


handler403 = agent_permission_denied
