from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from core.models import HospitalSettings
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
class HospitalProfileCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()
        cls.admin_group = Group.objects.get(name="Administrator")
        cls.doctor_group = Group.objects.get(name="Doctor")
        cls.patient_group, _ = Group.objects.get_or_create(name="Patient")

    def setUp(self):
        # Create standard test users
        self.admin_user = User.objects.create_user(
            username="admin_cms_user",
            email="admin@test.hms",
            password="StrongAdminPassword123!",
            is_staff=True,
        )
        self.admin_user.groups.add(self.admin_group)

        self.doctor_user = User.objects.create_user(
            username="doctor_user",
            email="doctor@test.hms",
            password="StrongDoctorPassword123!",
            is_staff=True,
        )
        self.doctor_user.groups.add(self.doctor_group)

        self.patient_user = User.objects.create_user(
            username="patient_user",
            email="patient@test.hms",
            password="StrongPatientPassword123!",
            is_staff=False,
        )
        self.patient_user.groups.add(self.patient_group)

        # Ensure canonical singleton profile exists
        self.settings_obj, _ = HospitalSettings.objects.get_or_create(
            pk=1,
            defaults={
                "name": "Canonical Test Hospital",
                "tagline": "Care and Compassion",
                "timezone": "Asia/Kolkata",
                "currency_code": "INR",
                "phone": "+91 94150 00000",
                "emergency_phone": "102",
                "emergency_phone_display": "102 / 108",
                "ambulance_phone": "108",
                "ambulance_phone_display": "108",
                "reception_phone": "+91 522 0000000",
                "reception_phone_display": "+91 (0522) 0000000",
                "email": "contact@canonical.test",
                "address": "123 Medical Enclave",
                "landmark": "Near Main Gate",
                "city": "Lucknow",
                "maps_query": "Test Hospital Lucknow",
            },
        )

    def test_singleton_changelist_redirects_to_singleton_change_view(self):
        """Accessing changelist redirects straight to singleton change form."""
        self.client.force_login(self.admin_user)
        response = self.client.get(
            "/admin/core/hospitalsettings/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertRedirects(response, "/admin/core/hospitalsettings/1/change/", fetch_redirect_response=False)

    def test_authorized_admin_can_view_hospital_profile(self):
        """Authorized Administrator can access the hospital profile change form."""
        self.client.force_login(self.admin_user)
        response = self.client.get(
            "/admin/core/hospitalsettings/1/change/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Canonical Test Hospital")
        self.assertContains(response, "Hospital Identity")
        self.assertContains(response, "Emergency &amp; Clinical Contacts")
        self.assertContains(response, "Localization &amp; Regional Settings")

    def test_authorized_admin_can_update_hospital_profile(self):
        """Authorized Administrator can update the canonical profile via POST."""
        self.client.force_login(self.admin_user)
        payload = {
            "name": "Updated Medical Center",
            "tagline": "World-Class Excellence",
            "timezone": "UTC",
            "currency_code": "USD",
            "phone": "+1 555 123 4567",
            "emergency_phone": "911",
            "emergency_phone_display": "911",
            "ambulance_phone": "911-AMB",
            "ambulance_phone_display": "911 (Ambulance)",
            "reception_phone": "+1 555 987 6543",
            "reception_phone_display": "+1 (555) 987-6543",
            "email": "info@updatedmed.test",
            "address": "456 Health Boulevard",
            "landmark": "Adjacent to Central Park",
            "city": "Metropolis",
            "maps_query": "Updated Medical Center Metropolis",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/hospitalsettings/1/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.name, "Updated Medical Center")
        self.assertEqual(self.settings_obj.tagline, "World-Class Excellence")
        self.assertEqual(self.settings_obj.timezone, "UTC")
        self.assertEqual(self.settings_obj.currency_code, "USD")
        self.assertEqual(self.settings_obj.phone, "+1 555 123 4567")
        self.assertEqual(self.settings_obj.email, "info@updatedmed.test")
        self.assertEqual(self.settings_obj.city, "Metropolis")

    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated requests are redirected to login."""
        response = self.client.get(
            "/admin/core/hospitalsettings/1/change/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/?next=/admin/core/hospitalsettings/1/change/", response.url)

    def test_unauthorized_portal_user_denied(self):
        """Non-admin portal users (e.g. Doctor, Patient) cannot access admin hospital settings."""
        self.client.force_login(self.doctor_user)
        response = self.client.get(
            "/admin/core/hospitalsettings/1/change/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.patient_user)
        response = self.client.get(
            "/admin/core/hospitalsettings/1/change/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_without_change_permission_cannot_post_updates(self):
        """Staff user with view-only permission cannot save changes."""
        view_only_user = User.objects.create_user(
            username="view_only_staff",
            email="view@test.hms",
            password="StrongStaffPassword123!",
            is_staff=True,
        )
        view_only_user.groups.add(self.admin_group)
        content_type = ContentType.objects.get_for_model(HospitalSettings)
        change_perm = Permission.objects.get(content_type=content_type, codename="change_hospitalsettings")
        self.admin_group.permissions.remove(change_perm)

        self.client.force_login(view_only_user)
        payload = {
            "name": "Unauthorized Modification Attempt",
            "timezone": "Asia/Kolkata",
            "currency_code": "INR",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/hospitalsettings/1/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)
        self.settings_obj.refresh_from_db()
        self.assertNotEqual(self.settings_obj.name, "Unauthorized Modification Attempt")
        self.assertEqual(self.settings_obj.name, "Canonical Test Hospital")

        # Restore permission
        self.admin_group.permissions.add(change_perm)

    def test_staff_without_view_permission_cannot_use_singleton_redirect(self):
        """The custom changelist redirect preserves Django's model permission boundary."""
        unprivileged_staff = User.objects.create_user(
            username="unprivileged_staff",
            password="StrongStaffPassword123!",
            is_staff=True,
        )
        self.client.force_login(unprivileged_staff)

        response = self.client.get(
            "/admin/core/hospitalsettings/",
            HTTP_HOST="admin.hms.test",
        )

        self.assertEqual(response.status_code, 403)

    def test_validation_empty_required_name(self):
        """Submitting empty or whitespace-only name fails validation and preserves existing data."""
        self.client.force_login(self.admin_user)
        payload = {
            "name": "   ",
            "timezone": "Asia/Kolkata",
            "currency_code": "INR",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/hospitalsettings/1/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("name", form.errors)
        self.assertIn("This field is required.", form.errors["name"])
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.name, "Canonical Test Hospital")

    def test_validation_invalid_timezone(self):
        """Submitting invalid timezone identifier raises validation error."""
        self.client.force_login(self.admin_user)
        payload = {
            "name": "Canonical Test Hospital",
            "timezone": "Mars/Olympus_Mons",
            "currency_code": "INR",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/hospitalsettings/1/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("timezone", form.errors)
        self.assertIn(
            "'Mars/Olympus_Mons' is not a valid IANA time zone identifier (e.g. Asia/Kolkata).",
            form.errors["timezone"],
        )
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.timezone, "Asia/Kolkata")

    def test_validation_invalid_currency_code(self):
        """Currency code must be 3-letter alphabetic ISO string."""
        self.client.force_login(self.admin_user)
        payload = {
            "name": "Canonical Test Hospital",
            "timezone": "Asia/Kolkata",
            "currency_code": "I12",
            "_save": "Save",
        }
        response = self.client.post(
            "/admin/core/hospitalsettings/1/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("currency_code", form.errors)
        self.assertIn(
            "Currency code must be a 3-letter ISO code (e.g. INR, USD).",
            form.errors["currency_code"],
        )
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.currency_code, "INR")

    def test_singleton_delete_is_forbidden(self):
        """Deletion of the canonical hospital profile is disabled."""
        self.client.force_login(self.admin_user)
        response = self.client.post(
            "/admin/core/hospitalsettings/1/delete/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(HospitalSettings.objects.filter(pk=1).exists())

    def test_cannot_add_duplicate_singleton(self):
        """Cannot add a second hospital profile."""
        self.client.force_login(self.admin_user)
        response = self.client.get(
            "/admin/core/hospitalsettings/add/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 403)

    def test_html_escaping_prevents_xss(self):
        """Malicious script input in hospital profile fields is escaped in rendered output."""
        self.client.force_login(self.admin_user)
        payload = {
            "name": "Safe Hospital <script>alert('xss')</script>",
            "tagline": "Compassion <b onmouseover='alert(1)'>Care</b>",
            "timezone": "Asia/Kolkata",
            "currency_code": "INR",
            "_save": "Save",
        }
        self.client.post(
            "/admin/core/hospitalsettings/1/change/",
            data=payload,
            HTTP_HOST="admin.hms.test",
        )
        self.settings_obj.refresh_from_db()
        self.assertIn("<script>", self.settings_obj.name)

        response = self.client.get(
            "/admin/core/hospitalsettings/1/change/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert('xss')</script>")
        self.assertContains(response, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")

    def test_public_android_api_reflects_updated_profile(self):
        """Android / public hospital info API contract is preserved and reflects CMS updates."""
        self.settings_obj.name = "API Verified Hospital"
        self.settings_obj.tagline = "API Verified Tagline"
        self.settings_obj.phone = "+91 99999 11111"
        self.settings_obj.emergency_phone = "112"
        self.settings_obj.save()

        # Android API is accessed on default root or any portal host
        response = self.client.get("/api/v1/hospital-info/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "API Verified Hospital")
        self.assertEqual(data["tagline"], "API Verified Tagline")
        self.assertEqual(data["phone"], "+91 99999 11111")
        self.assertEqual(data["emergency_phone"], "112")
