from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.models import (
    AuditEvent,
    HealthContent,
    HealthPackage,
    HospitalFacility,
    StaffProfile,
)
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
class PublicPublishingWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user (CMS Administrator)
        cls.admin_user = User.objects.create_user(
            username="admin_pub_user",
            email="admin_pub@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM-PUB-01",
        )

        # Doctor user (Clinical Reviewer)
        cls.doctor_user = User.objects.create_user(
            username="doctor_pub_user",
            email="doctor_pub@test.hms",
            password="DoctorPassword123!",
            is_staff=True,
        )
        doctor_group = Group.objects.get(name="Doctor")
        cls.doctor_user.groups.add(doctor_group)
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-PUB-01",
        )

        # Non-publishing staff user (Reception)
        cls.reception_user = User.objects.create_user(
            username="reception_pub_user",
            email="reception_pub@test.hms",
            password="ReceptionPassword123!",
            is_staff=True,
        )
        reception_group = Group.objects.get(name="Reception")
        cls.reception_user.groups.add(reception_group)

    def test_health_content_publishing_workflow_and_audit_trail(self):
        """Clinical reviewer publishing HealthContent creates audit event, draft is excluded from public API."""
        # 1. Author drafts article as Administrator
        article = HealthContent.objects.create(
            slug="stroke-symptoms-guide",
            title="Recognizing FAST Signs of Stroke",
            category="Neurology",
            summary="Emergency protocols and symptoms for rapid stroke identification.",
            body="Facial drooping, Arm weakness, Speech difficulty, Time to call emergency...",
            effective_from=date.today(),
            status=HealthContent.Status.DRAFT,
            author=self.admin_user,
        )

        # Confirm draft is NOT visible in public API
        response = self.client.get("/api/v1/health-content/")
        self.assertEqual(response.status_code, 200)
        slugs = [item["slug"] for item in response.json()]
        self.assertNotIn("stroke-symptoms-guide", slugs)

        # 2. Doctor / CMO publishes the article via admin change form
        self.client.force_login(self.doctor_user)
        post_data = {
            "slug": article.slug,
            "title": article.title,
            "category": article.category,
            "summary": article.summary,
            "body": article.body,
            "audience": "patients",
            "language": "en",
            "emergency_disclaimer": "Emergency immediate care needed.",
            "version": 1,
            "effective_from": article.effective_from.isoformat(),
            "status": HealthContent.Status.PUBLISHED,
            "author": self.admin_user.pk,
            "key_takeaways": "[]",
            "references": "[]",
        }
        res_pub = self.client.post(
            f"/admin/core/healthcontent/{article.pk}/change/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(res_pub.status_code, 200)
        article.refresh_from_db()
        self.assertEqual(article.status, HealthContent.Status.PUBLISHED)
        self.assertEqual(article.reviewer, self.doctor_user)

        # Confirm AuditEvent was generated
        audit = AuditEvent.objects.filter(
            target_type="healthcontent",
            target_id=str(article.pk),
            action="content.published",
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.doctor_profile)
        self.assertEqual(audit.details["new_status"], HealthContent.Status.PUBLISHED)

        # Confirm now visible in public API
        response2 = self.client.get("/api/v1/health-content/")
        self.assertEqual(response2.status_code, 200)
        slugs2 = [item["slug"] for item in response2.json()]
        self.assertIn("stroke-symptoms-guide", slugs2)

    def test_health_package_publish_and_unpublish_workflow(self):
        """Publishing/unpublishing HealthPackage updates public endpoint visibility and logs AuditEvent."""
        pkg = HealthPackage.objects.create(
            code="EXECUTIVE_SENIOR",
            name="Executive Senior Citizen Checkup",
            description="Comprehensive bundle designed for seniors aged 60+.",
            price=Decimal("1999.00"),
            valid_from=date.today(),
            is_published=False,
        )

        # Confirm not visible in public API
        res_pkg1 = self.client.get("/api/v1/health-packages/")
        self.assertEqual(res_pkg1.status_code, 200)
        codes1 = [item["code"] for item in res_pkg1.json()]
        self.assertNotIn("EXECUTIVE_SENIOR", codes1)

        # Publish via Admin
        self.client.force_login(self.admin_user)
        post_data = {
            "code": pkg.code,
            "name": pkg.name,
            "description": pkg.description,
            "price": "1999.00",
            "valid_from": date.today().isoformat(),
            "is_published": True,
        }
        res_edit = self.client.post(
            f"/admin/core/healthpackage/{pkg.pk}/change/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(res_edit.status_code, 200)
        pkg.refresh_from_db()
        self.assertTrue(pkg.is_published)

        # AuditEvent verified
        audit = AuditEvent.objects.filter(
            target_type="healthpackage",
            target_id=str(pkg.pk),
            action="healthpackage.published",
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.admin_profile)

        # Now visible in public API
        res_pkg2 = self.client.get("/api/v1/health-packages/")
        self.assertEqual(res_pkg2.status_code, 200)
        codes2 = [item["code"] for item in res_pkg2.json()]
        self.assertIn("EXECUTIVE_SENIOR", codes2)

    def test_facility_and_faq_activation_workflow_and_audit(self):
        """Activating and deactivating facilities/FAQs modifies public visibility with audit logs."""
        facility = HospitalFacility.objects.create(
            title="Advanced Chemotherapy Infusion Suite",
            category="Oncology",
            description="Daycare chemotherapy suite with laminar air flow and dedicated oncology nursing.",
            is_active=False,
        )

        # Verify not in public API
        res_fac1 = self.client.get("/api/v1/facilities/")
        self.assertEqual(res_fac1.status_code, 200)
        titles1 = [item["title"] for item in res_fac1.json()]
        self.assertNotIn("Advanced Chemotherapy Infusion Suite", titles1)

        # Activate via admin
        self.client.force_login(self.admin_user)
        post_data = {
            "title": facility.title,
            "category": facility.category,
            "description": facility.description,
            "display_order": 0,
            "is_active": "on",
        }
        res_act = self.client.post(
            f"/admin/core/hospitalfacility/{facility.pk}/change/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(res_act.status_code, 200)
        facility.refresh_from_db()
        self.assertTrue(facility.is_active)

        # Audit event checked
        audit = AuditEvent.objects.filter(
            target_type="hospitalfacility",
            target_id=str(facility.pk),
            action="facility.activated",
        ).first()
        self.assertIsNotNone(audit)

        # Now visible in public API
        res_fac2 = self.client.get("/api/v1/facilities/")
        self.assertEqual(res_fac2.status_code, 200)
        titles2 = [item["title"] for item in res_fac2.json()]
        self.assertIn("Advanced Chemotherapy Infusion Suite", titles2)

    def test_unauthorized_user_cannot_publish_content(self):
        """Unauthorized non-admin / non-clinical users cannot publish or modify public status."""
        self.client.force_login(self.reception_user)
        response = self.client.get("/admin/core/healthcontent/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)
