from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    Department,
    Patient,
    PatientAccount,
    PatientFeedback,
    StaffProfile,
    VisitType,
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
    ALLOWED_HOSTS=["testserver", ".hms.test"],
)
class PatientFeedbackWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Doctor
        cls.dept = Department.objects.create(name="General Medicine", code="MED-GEN", is_active=True)
        cls.doc_user = User.objects.create_user("dr_feedback", password="password", first_name="Vikas", last_name="Sharma")
        cls.doc_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-FB-01",
            department=cls.dept,
        )

        cls.visit_type = VisitType.objects.create(name="OPD Follow-up", code="OPD-FOL")

        # Patient 1: Alice (verified)
        cls.alice_user = User.objects.create_user(
            "alice_fb",
            email="alice@example.com",
            password="Password123!",
            first_name="Alice",
            last_name="Gupta",
        )
        cls.alice_patient = Patient.objects.create(
            mrn="MRN-ALICE-FB-01",
            full_name="Alice Gupta",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 28),
            phone="9876543210",
            email="alice@example.com",
        )
        cls.alice_account = PatientAccount.objects.create(
            user=cls.alice_user,
            patient=cls.alice_patient,
            is_verified=True,
        )

        # Patient 2: Bob (verified)
        cls.bob_user = User.objects.create_user(
            "bob_fb",
            email="bob@example.com",
            password="Password123!",
            first_name="Bob",
            last_name="Verma",
        )
        cls.bob_patient = Patient.objects.create(
            mrn="MRN-BOB-FB-01",
            full_name="Bob Verma",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 32),
            phone="9876543211",
            email="bob@example.com",
        )
        cls.bob_account = PatientAccount.objects.create(
            user=cls.bob_user,
            patient=cls.bob_patient,
            is_verified=True,
        )

        # Alice completed appointment 1 (already has feedback)
        cls.apt_alice_completed_1 = Appointment.objects.create(
            patient=cls.alice_patient,
            doctor=cls.doctor,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now() - timedelta(days=5),
            status=Appointment.Status.COMPLETED,
        )
        cls.alice_feedback_1 = PatientFeedback.objects.create(
            patient=cls.alice_patient,
            appointment=cls.apt_alice_completed_1,
            doctor=cls.doctor,
            rating=5,
            category=PatientFeedback.Category.DOCTOR_CONSULTATION,
            comment="Dr. Sharma explained everything with great empathy.",
            is_anonymous_public=True,
            status=PatientFeedback.Status.PUBLISHED,
        )

        # Alice completed appointment 2 (eligible for new feedback)
        cls.apt_alice_completed_2 = Appointment.objects.create(
            patient=cls.alice_patient,
            doctor=cls.doctor,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now() - timedelta(days=1),
            status=Appointment.Status.COMPLETED,
        )

        # Alice scheduled appointment (in progress/scheduled, NOT eligible)
        cls.apt_alice_scheduled = Appointment.objects.create(
            patient=cls.alice_patient,
            doctor=cls.doctor,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now() + timedelta(days=2),
            status=Appointment.Status.SCHEDULED,
        )

        # Bob completed appointment with feedback (isolation)
        cls.apt_bob_completed = Appointment.objects.create(
            patient=cls.bob_patient,
            doctor=cls.doctor,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now() - timedelta(days=3),
            status=Appointment.Status.COMPLETED,
        )
        cls.bob_feedback = PatientFeedback.objects.create(
            patient=cls.bob_patient,
            appointment=cls.apt_bob_completed,
            doctor=cls.doctor,
            rating=4,
            category=PatientFeedback.Category.OVERALL_EXPERIENCE,
            comment="Bob secret feedback experience.",
            is_anonymous_public=True,
            status=PatientFeedback.Status.PENDING,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get("/feedback/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

        resp_submit = self.client.post("/feedback/submit/", {})
        self.assertEqual(resp_submit.status_code, 302)
        self.assertIn("/accounts/login/", resp_submit.url)

    def test_unverified_patient_cannot_view_feedback(self):
        self.alice_account.is_verified = False
        self.alice_account.save(update_fields=["is_verified"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/feedback/")
        self.assertEqual(resp.status_code, 403)

    def test_archived_patient_cannot_view_feedback(self):
        self.alice_patient.archived_at = timezone.now()
        self.alice_patient.save(update_fields=["archived_at"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/feedback/")
        self.assertEqual(resp.status_code, 403)

    def test_feedback_workspace_shows_eligible_appointments_and_history(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get("/feedback/")
        self.assertEqual(resp.status_code, 200)

        # Alice's submitted feedback is visible
        self.assertContains(resp, "Dr. Vikas Sharma")
        self.assertContains(resp, "Dr. Sharma explained everything with great empathy.")
        self.assertContains(resp, "Published")

        # Eligible appointment 2 is shown in form selection
        self.assertContains(resp, f'<option value="{self.apt_alice_completed_2.id}" class="eligible-apt-option">')

        # Already submitted appointment 1 and scheduled appointment are NOT in form options
        self.assertNotContains(resp, f'<option value="{self.apt_alice_completed_1.id}" class="eligible-apt-option">')
        self.assertNotContains(resp, f'<option value="{self.apt_alice_scheduled.id}" class="eligible-apt-option">')

        # Bob's feedback must NOT leak
        self.assertNotContains(resp, "Bob secret feedback experience.")

    def test_submit_valid_feedback_success(self):
        self.client.force_login(self.alice_user)
        resp = self.client.post(
            "/feedback/submit/",
            {
                "appointment": self.apt_alice_completed_2.id,
                "rating": "4",
                "category": PatientFeedback.Category.DOCTOR_CONSULTATION,
                "comment": "Very thorough checkup and clear advice.",
                "is_anonymous_public": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/feedback/")

        # Verify feedback in database
        fb = PatientFeedback.objects.get(appointment=self.apt_alice_completed_2)
        self.assertEqual(fb.patient, self.alice_patient)
        self.assertEqual(fb.doctor, self.doctor)
        self.assertEqual(fb.rating, 4)
        self.assertEqual(fb.comment, "Very thorough checkup and clear advice.")
        self.assertTrue(fb.is_anonymous_public)
        self.assertEqual(fb.status, PatientFeedback.Status.PENDING)

    def test_duplicate_feedback_prevented(self):
        self.client.force_login(self.alice_user)
        resp = self.client.post(
            "/feedback/submit/",
            {
                "appointment": self.apt_alice_completed_1.id,  # already has feedback
                "rating": "5",
                "category": PatientFeedback.Category.DOCTOR_CONSULTATION,
                "comment": "Duplicate attempt",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/feedback/")

    def test_cross_patient_appointment_feedback_returns_404(self):
        self.client.force_login(self.alice_user)
        # Alice tries to submit feedback for Bob's appointment
        resp = self.client.post(
            "/feedback/submit/",
            {
                "appointment": self.apt_bob_completed.id,
                "rating": "5",
                "category": PatientFeedback.Category.DOCTOR_CONSULTATION,
            },
        )
        self.assertEqual(resp.status_code, 404)
