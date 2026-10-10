from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.forms import HealthContentForm
from core.models import HealthContent
from core.roles import configure_role_permissions

User = get_user_model()


@override_settings(
    PORTAL_HOSTS={
        "admin": "admin.hms.test",
        "staff": "staff.hms.test",
        "store": "store.hms.test",
        "patient": "patient.hms.test",
        "agent": "agent.hms.test",
    },
    ALLOWED_HOSTS=["*"],
)
class WebsiteContentCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user (without clinical publish permission)
        cls.admin_user = User.objects.create_user(
            username="admin_content_user",
            email="admin_content@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Doctor user (has clinical publish permission)
        cls.doctor_user = User.objects.create_user(
            username="doctor_content_user",
            email="doctor_content@test.hms",
            password="DoctorPassword123!",
            is_staff=True,
        )
        doctor_group = Group.objects.get(name="Doctor")
        cls.doctor_user.groups.add(doctor_group)

        # Doctor with both Admin & Doctor roles
        cls.admin_doctor_user = User.objects.create_user(
            username="chief_medical_officer",
            email="cmo@test.hms",
            password="CmoPassword123!",
            is_staff=True,
        )
        cls.admin_doctor_user.groups.add(admin_group, doctor_group)

        # Non-clinical staff (Reception)
        cls.reception_user = User.objects.create_user(
            username="reception_content_user",
            email="reception_content@test.hms",
            password="ReceptionPassword123!",
            is_staff=True,
        )
        reception_group = Group.objects.get(name="Reception")
        cls.reception_user.groups.add(reception_group)

        # Existing draft article
        cls.draft_article = HealthContent.objects.create(
            slug="cardiac-health-tips",
            title="Everyday Habits for a Healthy Heart",
            category="Cardiology",
            summary="A quick guide to cardiovascular care and blood pressure monitoring.",
            body="Cardiovascular wellness begins with balanced nutrition, regular exercise...",
            effective_from=date.today(),
            status=HealthContent.Status.DRAFT,
            author=cls.admin_user,
        )

        # Existing published article
        cls.published_article = HealthContent.objects.create(
            slug="diabetes-management-guide",
            title="Understanding Type 2 Diabetes Management",
            category="Endocrinology",
            summary="Patient guidelines on glycemic index, insulin adherence, and regular screening.",
            body="Type 2 diabetes requires consistent tracking of blood glucose...",
            effective_from=date.today() - timedelta(days=1),
            status=HealthContent.Status.PUBLISHED,
            author=cls.admin_user,
            reviewer=cls.doctor_user,
            reviewed_at=timezone.now(),
        )

    def test_authorized_admin_can_view_content_changelist(self):
        """Admin can access HealthContent changelist in admin portal."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/healthcontent/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cardiac-health-tips")
        self.assertContains(response, "diabetes-management-guide")

    def test_unauthorized_staff_cannot_access_health_content_cms(self):
        """Reception staff cannot access HealthContent CMS."""
        self.client.force_login(self.reception_user)
        response = self.client.get("/admin/core/healthcontent/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_draft_health_content(self):
        """Administrator can draft health content without immediate clinical review."""
        self.client.force_login(self.admin_user)
        post_data = {
            "slug": "pediatric-vaccine-schedule",
            "title": "Essential Childhood Immunization Schedule",
            "category": "Pediatrics",
            "summary": "Key vaccines needed from birth to age 12.",
            "body": "Vaccinations prevent debilitating infections such as measles and polio...",
            "audience": "parents",
            "language": "en",
            "emergency_disclaimer": "For allergic reactions post-shot, consult emergency OPD immediately.",
            "version": 1,
            "effective_from": date.today().isoformat(),
            "status": HealthContent.Status.DRAFT,
            "author": self.admin_user.pk,
            "key_takeaways": "[]",
            "references": "[]",
        }
        response = self.client.post(
            "/admin/core/healthcontent/add/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        article = HealthContent.objects.get(slug="pediatric-vaccine-schedule")
        self.assertEqual(article.status, HealthContent.Status.DRAFT)
        self.assertIsNone(article.reviewer)

    def test_admin_without_clinical_permission_cannot_directly_publish(self):
        """Admin without core.publish_healthcontent cannot publish an article directly."""
        self.client.force_login(self.admin_user)
        post_data = {
            "slug": "unreviewed-medical-advice",
            "title": "Unreviewed Experimental Protocol",
            "category": "Experimental",
            "summary": "Summary text",
            "body": "Body text",
            "audience": "patients",
            "language": "en",
            "emergency_disclaimer": "Emergency disclaimer",
            "version": 1,
            "effective_from": date.today().isoformat(),
            "status": HealthContent.Status.PUBLISHED,
            "author": self.admin_user.pk,
            "key_takeaways": "[]",
            "references": "[]",
        }
        response = self.client.post(
            "/admin/core/healthcontent/add/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
        )
        # Should be forbidden with PermissionDenied (403)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(HealthContent.objects.filter(slug="unreviewed-medical-advice").exists())

    def test_clinician_with_publishing_permission_can_publish_article(self):
        """User with core.publish_healthcontent can publish and becomes the recorded reviewer."""
        self.client.force_login(self.admin_doctor_user)
        post_data = {
            "slug": "hypertension-monitoring",
            "title": "Hypertension Home Blood Pressure Protocols",
            "category": "Cardiology",
            "summary": "Protocol for logging blood pressure measurements accurately at home.",
            "body": "Patients should rest seated for 5 minutes prior to measuring blood pressure...",
            "audience": "patients",
            "language": "en",
            "emergency_disclaimer": "If systolic reading exceeds 180 mmHg, contact emergency triage.",
            "version": 1,
            "effective_from": date.today().isoformat(),
            "status": HealthContent.Status.PUBLISHED,
            "author": self.admin_user.pk,
            "key_takeaways": "[]",
            "references": "[]",
        }
        response = self.client.post(
            "/admin/core/healthcontent/add/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        article = HealthContent.objects.get(slug="hypertension-monitoring")
        self.assertEqual(article.status, HealthContent.Status.PUBLISHED)
        self.assertEqual(article.reviewer, self.admin_doctor_user)
        self.assertIsNotNone(article.reviewed_at)

    def test_form_validation_duplicate_slug(self):
        """Form rejects duplicate slug case-insensitively."""
        form = HealthContentForm(data={
            "slug": "CARDIAC-HEALTH-TIPS",
            "title": "New Title",
            "effective_from": date.today(),
            "status": HealthContent.Status.DRAFT,
            "author": self.admin_user.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("slug", form.errors)
        self.assertIn("already exists", form.errors["slug"][0])

    def test_form_validation_invalid_date_range(self):
        """Form rejects expires_on earlier than effective_from."""
        form = HealthContentForm(data={
            "slug": "date-validation-check",
            "title": "Date Validation Check",
            "effective_from": date.today(),
            "expires_on": date.today() - timedelta(days=2),
            "status": HealthContent.Status.DRAFT,
            "author": self.admin_user.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("expires_on", form.errors)
        self.assertIn("on or after", form.errors["expires_on"][0])

    def test_public_api_exposes_only_published_content_without_sensitive_info(self):
        """Public API endpoint exposes published articles without author internal credentials or drafts."""
        response = self.client.get("/api/v1/health-content/")
        self.assertEqual(response.status_code, 200)
        results = response.json()
        slugs = [item["slug"] for item in results]
        self.assertIn("diabetes-management-guide", slugs)
        self.assertNotIn("cardiac-health-tips", slugs)  # draft is excluded

        # Verify no sensitive clinical or internal fields exposed
        item = next(i for i in results if i["slug"] == "diabetes-management-guide")
        self.assertNotIn("author", item)
        self.assertNotIn("ai_prompt_version", item)
        self.assertEqual(item["reviewer"], self.doctor_user.username)
