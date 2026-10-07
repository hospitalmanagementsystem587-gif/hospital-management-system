from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import get_urlconf
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
class PortalArchitectureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name in ("Administrator", "Doctor", "Reception", "Pharmacy"):
            Group.objects.create(name=name)

        cls.doctor = User.objects.create_user("doctor")
        cls.doctor.groups.add(Group.objects.get(name="Doctor"))
        cls.pharmacist = User.objects.create_user("pharmacist")
        cls.pharmacist.groups.add(Group.objects.get(name="Pharmacy"))
        cls.administrator = User.objects.create_user("administrator", is_staff=True)
        cls.administrator.groups.add(Group.objects.get(name="Administrator"))
        cls.patient_user = User.objects.create_user("patient")
        patient = Patient.objects.create(mrn="KAN35-001", full_name="Portal Patient")
        PatientAccount.objects.create(
            user=cls.patient_user, patient=patient, is_verified=True
        )
        cls.unverified_user = User.objects.create_user("unverified")
        unverified_patient = Patient.objects.create(
            mrn="KAN35-002", full_name="Unverified Portal Patient"
        )
        PatientAccount.objects.create(
            user=cls.unverified_user,
            patient=unverified_patient,
            is_verified=False,
        )
        cls.archived_user = User.objects.create_user("archived")
        archived_patient = Patient.objects.create(
            mrn="KAN35-003",
            full_name="Archived Portal Patient",
            archived_at=timezone.now(),
        )
        PatientAccount.objects.create(
            user=cls.archived_user,
            patient=archived_patient,
            is_verified=True,
        )
        cls.ordinary_user = User.objects.create_user("ordinary")

    def test_anonymous_portal_requests_redirect_to_shared_django_login(self):
        response = self.client.get("/", HTTP_HOST="staff.hms.test:8443")
        self.assertRedirects(
            response,
            "/accounts/login/?next=/",
            fetch_redirect_response=False,
        )

    def test_staff_portal_accepts_staff_group_and_rejects_ordinary_user(self):
        self.client.force_login(self.doctor)
        self.assertEqual(
            self.client.get("/__portal__/", HTTP_HOST="staff.hms.test").status_code,
            200,
        )

        self.client.force_login(self.ordinary_user)
        self.assertEqual(
            self.client.get("/__portal__/", HTTP_HOST="staff.hms.test").status_code,
            403,
        )

    def test_store_portal_is_restricted_to_pharmacy_and_administrators(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get("/", HTTP_HOST="store.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Store portal")

        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get("/", HTTP_HOST="store.hms.test").status_code, 403)

    def test_patient_portal_requires_verified_patient_mapping(self):
        self.client.force_login(self.patient_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="patient.hms.test").status_code, 200)

        self.client.force_login(self.ordinary_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="patient.hms.test").status_code, 403)

        for user in (self.unverified_user, self.archived_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get("/", HTTP_HOST="patient.hms.test").status_code,
                    403,
                )

    def test_admin_and_agent_boundaries_fail_closed(self):
        self.client.force_login(self.administrator)
        self.assertRedirects(
            self.client.get("/", HTTP_HOST="admin.hms.test"),
            "/admin/",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.get("/", HTTP_HOST="agent.hms.test").status_code, 200)

        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get("/", HTTP_HOST="admin.hms.test").status_code, 403)
        self.assertEqual(self.client.get("/", HTTP_HOST="agent.hms.test").status_code, 403)

    def test_unknown_host_uses_legacy_application(self):
        self.client.force_login(self.pharmacist)
        self.client.get("/", HTTP_HOST="store.hms.test")
        self.assertIsNone(get_urlconf())

        response = self.client.get("/health/", HTTP_HOST="legacy.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.wsgi_request.portal)

    def test_android_api_contract_is_host_neutral(self):
        for host in (
            "admin.hms.test",
            "staff.hms.test",
            "store.hms.test",
            "patient.hms.test",
            "agent.hms.test",
        ):
            with self.subTest(host=host):
                response = self.client.get("/api/v1/bed-availability/", HTTP_HOST=host)
                self.assertEqual(response.status_code, 200)
