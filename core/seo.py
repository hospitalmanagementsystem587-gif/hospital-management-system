from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from core.models import HospitalSettings


class PublicSitemap(Sitemap):
    """The intentionally small set of canonical, public HTML pages."""

    changefreq = "weekly"
    priority = 1.0

    def items(self):
        return ["home"]

    def location(self, item):
        return reverse(item)

    def lastmod(self, item):
        hospital = HospitalSettings.objects.filter(pk=1).only("updated_at").first()
        return hospital.updated_at if hospital else None

    def get_protocol(self, protocol=None):
        return urlsplit(settings.PUBLIC_SITE_URL).scheme

    def get_domain(self, site=None):
        return urlsplit(settings.PUBLIC_SITE_URL).netloc


public_sitemaps = {"public": PublicSitemap}


class NoIndexPrivateResponsesMiddleware:
    """Keep authenticated, portal, API, and utility URLs out of search results."""

    public_paths = frozenset({"/", "/robots.txt", "/sitemap.xml"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        is_public_home = (
            request.path == "/"
            and getattr(request, "portal", None) is None
            and not getattr(request.user, "is_authenticated", False)
        )
        if request.path not in self.public_paths or (
            request.path == "/" and not is_public_home
        ):
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
