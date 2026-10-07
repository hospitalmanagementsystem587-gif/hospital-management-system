from django.urls import path

from config.urls import urlpatterns as legacy_urlpatterns
from core.portal.views import portal_home


# The existing server-rendered HMS is the staff workspace during the portal
# migration. Keeping the same patterns preserves all current links and names.
urlpatterns = [path("__portal__/", portal_home, name="staff_portal_boundary")]
urlpatterns += legacy_urlpatterns
