import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import HospitalSettings


@override_settings(
    PUBLIC_SITE_URL="https://hospital.example",
    GOOGLE_SITE_VERIFICATION="google-token",
)
class PublicSeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        HospitalSettings.objects.update_or_create(
            pk=1,
            defaults={
                "name": "Vedant Hospital",
                "phone": "+91 12345 67890",
                "email": "care@example.com",
                "address": "Hardoi Road",
                "city": "Lucknow",
            },
        )

    def test_public_home_has_complete_indexable_metadata_and_one_h1(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, '<link rel="canonical" href="https://hospital.example/">')
        self.assertContains(response, '<meta name="robots" content="index,follow,max-image-preview:large">')
        self.assertContains(response, '<meta name="description"')
        self.assertContains(response, 'property="og:image"')
        self.assertContains(response, 'name="google-site-verification" content="google-token"')
        self.assertEqual(len(re.findall(r"<h1(?:\s|>)", html, re.IGNORECASE)), 1)
        self.assertNotIn("X-Robots-Tag", response)

        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        self.assertIsNotNone(match)
        schema = json.loads(match.group(1))
        self.assertEqual(schema["@type"], "Hospital")
        self.assertEqual(schema["url"], "https://hospital.example/")

    def test_schema_data_cannot_close_its_script_element(self):
        hospital = HospitalSettings.objects.get(pk=1)
        hospital.name = "Clinic </script><script>alert(1)</script>"
        hospital.save(update_fields=["name"])
        html = self.client.get("/").content.decode()
        schema_body = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        ).group(1)
        self.assertNotIn("</script>", schema_body)
        self.assertIn(r"\u003c/script\u003e", schema_body)
        json.loads(schema_body)

    def test_sitemap_has_only_canonical_public_home(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        body = response.content.decode()
        self.assertIn("https://hospital.example/", body)
        for private_path in ("/api/", "/admin/", "/patients/", "/accounts/"):
            self.assertNotIn(private_path, body)

    def test_robots_references_sitemap_and_blocks_private_routes(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertContains(response, "Allow: /$")
        self.assertContains(response, "Disallow: /api/")
        self.assertContains(response, "Disallow: /patients/")
        self.assertContains(response, "Sitemap: https://hospital.example/sitemap.xml")

    def test_private_html_and_api_have_noindex_header(self):
        login = self.client.get("/accounts/login/")
        self.assertEqual(login["X-Robots-Tag"], "noindex, nofollow, noarchive")
        api = self.client.get("/api/v1/hospital-info/")
        self.assertEqual(api["X-Robots-Tag"], "noindex, nofollow, noarchive")

    def test_authenticated_home_is_not_indexable(self):
        user = get_user_model().objects.create_user("seo-user", password="test-password")
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertContains(response, '<meta name="robots" content="noindex,nofollow,noarchive">')
        self.assertNotContains(response, 'rel="canonical"')
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")

    def test_portal_redirect_is_not_indexable(self):
        response = self.client.get("/", HTTP_HOST="staff.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")
