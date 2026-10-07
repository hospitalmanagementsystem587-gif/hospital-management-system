from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import Patient, PatientAccount


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
class SharedAuthSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name in ("Administrator", "Doctor", "Reception", "Pharmacy"):
            Group.objects.create(name=name)

        cls.password = "HospitalPass123!"
        cls.doctor = User.objects.create_user(
            username="doctor_auth",
            email="doctor@hms.test",
            password=cls.password,
        )
        cls.doctor.groups.add(Group.objects.get(name="Doctor"))

        cls.pharmacist = User.objects.create_user(
            username="pharmacist_auth",
            email="pharmacy@hms.test",
            password=cls.password,
        )
        cls.pharmacist.groups.add(Group.objects.get(name="Pharmacy"))

        cls.admin_user = User.objects.create_user(
            username="admin_auth",
            email="admin@hms.test",
            password=cls.password,
            is_staff=True,
        )
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))

        cls.patient_user = User.objects.create_user(
            username="patient_auth",
            email="patient@hms.test",
            password=cls.password,
        )
        patient = Patient.objects.create(mrn="AUTH-001", full_name="Auth Patient")
        PatientAccount.objects.create(
            user=cls.patient_user, patient=patient, is_verified=True
        )

        cls.inactive_user = User.objects.create_user(
            username="inactive_auth",
            email="inactive@hms.test",
            password=cls.password,
            is_active=False,
        )
        cls.inactive_user.groups.add(Group.objects.get(name="Doctor"))

    def test_login_and_logout_across_all_portals(self):
        hosts_and_users = [
            ("admin.hms.test", self.admin_user, "/admin/"),
            ("staff.hms.test", self.doctor, "/"),
            ("store.hms.test", self.pharmacist, "/"),
            ("patient.hms.test", self.patient_user, "/"),
            ("agent.hms.test", self.admin_user, "/"),
        ]

        for host, user, expected_target in hosts_and_users:
            with self.subTest(host=host, user=user.username):
                client = Client()

                # Anonymous redirect to portal-local login with next param
                res_anon = client.get("/", HTTP_HOST=host)
                self.assertEqual(res_anon.status_code, 302)
                self.assertIn("/accounts/login/?next=/", res_anon.url)

                # Successful login
                res_login = client.post(
                    "/accounts/login/",
                    {"username": user.username, "password": self.password},
                    HTTP_HOST=host,
                )
                self.assertEqual(res_login.status_code, 302)
                # Next defaults to '/' or login redirect
                self.assertIn("_auth_user_id", client.session)

                # Access target portal authenticated
                res_auth = client.get("/", HTTP_HOST=host)
                if host == "admin.hms.test":
                    self.assertEqual(res_auth.status_code, 302)
                    self.assertIn("/admin/", res_auth.url)
                else:
                    self.assertEqual(res_auth.status_code, 200)

                # Secure POST logout
                res_logout = client.post("/accounts/logout/", HTTP_HOST=host)
                self.assertEqual(res_logout.status_code, 302)
                self.assertNotIn("_auth_user_id", client.session)

    def test_safe_next_redirect_and_untrusted_rejection(self):
        client = Client()
        # Safe relative redirect
        res = client.post(
            "/accounts/login/",
            {
                "username": self.doctor.username,
                "password": self.password,
                "next": "/appointments/",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, "/appointments/")

        # Untrusted external redirect should be ignored (falls back to default success URL)
        client = Client()
        res_unsafe = client.post(
            "/accounts/login/",
            {
                "username": self.doctor.username,
                "password": self.password,
                "next": "https://evil.com/phishing",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_unsafe.status_code, 302)
        self.assertNotIn("evil.com", res_unsafe.url)
        self.assertEqual(res_unsafe.url, "/")

    def test_inactive_user_cannot_login_or_access_portal(self):
        for host in ("admin.hms.test", "staff.hms.test", "patient.hms.test"):
            with self.subTest(host=host):
                client = Client()
                res = client.post(
                    "/accounts/login/",
                    {
                        "username": self.inactive_user.username,
                        "password": self.password,
                    },
                    HTTP_HOST=host,
                )
                self.assertEqual(res.status_code, 200)
                self.assertNotIn("_auth_user_id", client.session)

    def test_session_cookie_settings_and_subdomain_policy(self):
        # By default SESSION_COOKIE_DOMAIN is None (strict per-host)
        client = Client()
        client.post(
            "/accounts/login/",
            {"username": self.doctor.username, "password": self.password},
            HTTP_HOST="staff.hms.test",
        )
        session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
        self.assertIsNotNone(session_cookie)
        self.assertTrue(session_cookie["httponly"])
        self.assertEqual(session_cookie["samesite"].lower(), "lax")

    @override_settings(
        SESSION_COOKIE_DOMAIN=".hms.test",
        CSRF_COOKIE_DOMAIN=".hms.test",
    )
    def test_cross_subdomain_session_sharing_policy(self):
        # When SESSION_COOKIE_DOMAIN is set, the session cookie domain is set to .hms.test
        client = Client()
        client.post(
            "/accounts/login/",
            {"username": self.admin_user.username, "password": self.password},
            HTTP_HOST="admin.hms.test",
        )
        session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
        self.assertIsNotNone(session_cookie)
        self.assertEqual(session_cookie["domain"], ".hms.test")

        # Admin user can access agent.hms.test and staff.hms.test using same session
        res_agent = client.get("/", HTTP_HOST="agent.hms.test")
        self.assertEqual(res_agent.status_code, 200)

    def test_portal_context_processor(self):
        client = Client()
        client.force_login(self.doctor)
        res = client.get("/health/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.wsgi_request.portal, "staff")
