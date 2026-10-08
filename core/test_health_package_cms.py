from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.forms import HealthPackageForm
from core.models import HealthPackage, Service
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
class HealthPackageCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_pkg_user",
            email="admin_pkg@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Non-admin staff user (Reception)
        cls.reception_user = User.objects.create_user(
            username="reception_pkg_user",
            email="reception_pkg@test.hms",
            password="ReceptionPassword123!",
            is_staff=True,
        )
        reception_group = Group.objects.get(name="Reception")
        cls.reception_user.groups.add(reception_group)

        # Baseline services
        cls.srv_cbc = Service.objects.create(
            code="SRV_CBC",
            name="Complete Blood Count",
            current_charge=Decimal("450.00"),
            is_active=True,
        )
        cls.srv_ecg = Service.objects.create(
            code="SRV_ECG",
            name="12-Lead Electrocardiogram",
            current_charge=Decimal("600.00"),
            is_active=True,
        )

        # Baseline health package
        cls.package = HealthPackage.objects.create(
            code="BASIC_HEALTH",
            name="Basic Annual Health Checkup",
            description="Essential diagnostic bundle for routine health maintenance.",
            price=Decimal("899.00"),
            eligibility="All adults aged 18 and older",
            fasting_instructions="Overnight fasting 10-12 hours required",
            valid_from=date.today(),
            valid_until=date.today() + timedelta(days=90),
            is_published=True,
        )
        cls.package.included_services.set([cls.srv_cbc, cls.srv_ecg])

    def test_authorized_admin_can_view_health_package_changelist(self):
        """Admin can view the health packages changelist with price and publish status."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/healthpackage/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BASIC_HEALTH")
        self.assertContains(response, "Basic Annual Health Checkup")
        self.assertContains(response, "899.00")

    def test_unauthorized_staff_cannot_change_health_packages(self):
        """Reception staff without healthpackage change permissions cannot access the change form."""
        self.client.force_login(self.reception_user)
        response = self.client.get(
            f"/admin/core/healthpackage/{self.package.pk}/change/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_health_package_with_included_services(self):
        """Admin can create a new health package bundled with multiple catalog services."""
        self.client.force_login(self.admin_user)
        post_data = {
            "code": "EXEC_CARDIAC",
            "name": "Executive Cardiac Wellness",
            "description": "Comprehensive cardiac and vascular screening package.",
            "price": "1499.00",
            "eligibility": "Adults aged 35+",
            "fasting_instructions": "12 hours water-only fasting",
            "valid_from": date.today().isoformat(),
            "valid_until": (date.today() + timedelta(days=60)).isoformat(),
            "is_published": "on",
            "included_services": [self.srv_cbc.pk, self.srv_ecg.pk],
        }
        response = self.client.post(
            "/admin/core/healthpackage/add/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        new_pkg = HealthPackage.objects.get(code="EXEC_CARDIAC")
        self.assertEqual(new_pkg.name, "Executive Cardiac Wellness")
        self.assertEqual(new_pkg.price, Decimal("1499.00"))
        self.assertTrue(new_pkg.is_published)
        self.assertEqual(set(new_pkg.included_services.all()), {self.srv_cbc, self.srv_ecg})

    def test_form_validation_duplicate_code(self):
        """Form enforces unique package code case-insensitively."""
        form = HealthPackageForm(data={
            "code": "basic_health",
            "name": "Different Name",
            "price": "999.00",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)
        self.assertIn("already exists", form.errors["code"][0])

    def test_form_validation_duplicate_name(self):
        """Form enforces unique package name case-insensitively."""
        form = HealthPackageForm(data={
            "code": "NEW_CODE",
            "name": "basic annual health checkup",
            "price": "999.00",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("already exists", form.errors["name"][0])

    def test_form_validation_negative_price(self):
        """Form rejects negative pricing."""
        form = HealthPackageForm(data={
            "code": "TEST_PRICE",
            "name": "Test Package",
            "price": "-50.00",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_form_validation_invalid_validity_date_range(self):
        """Form rejects valid_until that is before valid_from."""
        form = HealthPackageForm(data={
            "code": "DATE_TEST",
            "name": "Date Test Package",
            "price": "500.00",
            "valid_from": date.today(),
            "valid_until": date.today() - timedelta(days=5),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("valid_until", form.errors)
        self.assertIn("on or after", form.errors["valid_until"][0])

    def test_admin_can_update_package_status_and_price(self):
        """Admin can modify existing package publishing state and discount price."""
        self.client.force_login(self.admin_user)
        change_data = {
            "code": self.package.code,
            "name": self.package.name,
            "description": "Updated description text.",
            "price": "799.00",
            "eligibility": self.package.eligibility,
            "fasting_instructions": self.package.fasting_instructions,
            "valid_from": self.package.valid_from.isoformat() if self.package.valid_from else "",
            "valid_until": self.package.valid_until.isoformat() if self.package.valid_until else "",
            # is_published omitted means False
            "included_services": [self.srv_cbc.pk],
        }
        response = self.client.post(
            f"/admin/core/healthpackage/{self.package.pk}/change/",
            data=change_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.package.refresh_from_db()
        self.assertEqual(self.package.price, Decimal("799.00"))
        self.assertFalse(self.package.is_published)
        self.assertEqual(list(self.package.included_services.all()), [self.srv_cbc])
