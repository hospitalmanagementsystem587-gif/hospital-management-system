from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import Patient, PatientAccount, StaffProfile
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
    ALLOWED_HOSTS=["testserver", ".hms.test"],
)
class PatientWebAuthenticationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        configure_role_permissions()

        cls.password = "Secr3tP@ssw0rd!"

        # 1. Verified Patient User & Account
        cls.patient_user = User.objects.create_user(
            username="patient_jane",
            email="jane.doe@example.com",
            password=cls.password,
        )
        cls.patient = Patient.objects.create(
            mrn="PAT-AUTH-001",
            full_name="Jane Doe",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 28),
            phone="+919876543210",
        )
        cls.patient_account = PatientAccount.objects.create(
            user=cls.patient_user,
            patient=cls.patient,
            is_verified=True,
            phone_verified=True,
        )

        # 2. Unverified Patient User
        cls.unverified_user = User.objects.create_user(
            username="patient_unverified",
            email="unverified@example.com",
            password=cls.password,
        )
        cls.unverified_patient = Patient.objects.create(
            mrn="PAT-AUTH-002",
            full_name="Unverified User",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 30),
            phone="+919876543211",
        )
        cls.unverified_account = PatientAccount.objects.create(
            user=cls.unverified_user,
            patient=cls.unverified_patient,
            is_verified=False,
        )

        # 3. Archived Patient User
        cls.archived_user = User.objects.create_user(
            username="patient_archived",
            email="archived@example.com",
            password=cls.password,
        )
        cls.archived_patient = Patient.objects.create(
            mrn="PAT-AUTH-003",
            full_name="Archived Patient",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 40),
            phone="+919876543212",
            archived_at=timezone.now(),
        )
        cls.archived_account = PatientAccount.objects.create(
            user=cls.archived_user,
            patient=cls.archived_patient,
            is_verified=True,
        )

        # 4. Hospital Doctor User (Staff)
        cls.doctor_user = User.objects.create_user(
            username="doctor_auth_staff",
            email="doctor@hospital.internal",
            password=cls.password,
        )
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-AUTH-1",
        )

    def setUp(self):
        cache.clear()

    def test_unauthenticated_patient_portal_redirects_to_login(self):
        client = Client()
        res = client.get("/", HTTP_HOST="patient.hms.test")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login/?next=/", res.url)

    def test_patient_login_page_renders_with_patient_branding_and_csrf(self):
        client = Client()
        res = client.get("/accounts/login/", HTTP_HOST="patient.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Patient sign in")
        self.assertContains(res, "Patient Portal")
        self.assertContains(res, "Personal Health Record")
        self.assertContains(res, "csrfmiddlewaretoken")

    def test_successful_verified_patient_login(self):
        client = Client()
        res = client.post(
            "/accounts/login/",
            {"username": "patient_jane", "password": self.password},
            HTTP_HOST="patient.hms.test",
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn("_auth_user_id", client.session)

        # Authenticated access to patient portal succeeds
        res_home = client.get("/", HTTP_HOST="patient.hms.test")
        self.assertEqual(res_home.status_code, 200)

    def test_unverified_or_archived_patient_login_denied_portal_access(self):
        client = Client()
        res = client.post(
            "/accounts/login/",
            {"username": "patient_unverified", "password": self.password},
            HTTP_HOST="patient.hms.test",
        )
        self.assertEqual(res.status_code, 302)
        res_access = client.get("/", HTTP_HOST="patient.hms.test")
        self.assertEqual(res_access.status_code, 403)

        client_archived = Client()
        res_arc = client_archived.post(
            "/accounts/login/",
            {"username": "patient_archived", "password": self.password},
            HTTP_HOST="patient.hms.test",
        )
        self.assertEqual(res_arc.status_code, 302)
        res_arc_access = client_archived.get("/", HTTP_HOST="patient.hms.test")
        self.assertEqual(res_arc_access.status_code, 403)

    def test_staff_user_without_verified_patient_account_denied_patient_portal(self):
        client = Client()
        res = client.post(
            "/accounts/login/",
            {"username": "doctor_auth_staff", "password": self.password},
            HTTP_HOST="patient.hms.test",
        )
        self.assertEqual(res.status_code, 302)
        res_access = client.get("/", HTTP_HOST="patient.hms.test")
        self.assertEqual(res_access.status_code, 403)

    def test_login_rate_limiting_protects_against_brute_force(self):
        client = Client()
        for i in range(4):
            res = client.post(
                "/accounts/login/",
                {"username": "patient_jane", "password": "wrongpassword"},
                HTTP_HOST="patient.hms.test",
            )
            self.assertEqual(res.status_code, 200)

        # 5th failed attempt triggers HTTP 429
        res_throttled = client.post(
            "/accounts/login/",
            {"username": "patient_jane", "password": "wrongpassword"},
            HTTP_HOST="patient.hms.test",
        )
        self.assertEqual(res_throttled.status_code, 429)

    def test_secure_patient_logout(self):
        client = Client()
        client.force_login(self.patient_user)
        self.assertIn("_auth_user_id", client.session)

        res_logout = client.post("/accounts/logout/", HTTP_HOST="patient.hms.test")
        self.assertEqual(res_logout.status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)
