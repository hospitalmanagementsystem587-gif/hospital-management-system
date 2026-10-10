from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    AuditEvent,
    Consultation,
    Medicine,
    NumberSequence,
    Patient,
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
class DoctorConsultationWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        NumberSequence.objects.create(
            code="PRESCRIPTION",
            prefix="RX-",
            next_value=100,
        )

        # Attending Doctor 1
        cls.doc1_user = User.objects.create_user("doc1_user", password="password")
        cls.doc1_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc1_profile = StaffProfile.objects.create(
            user=cls.doc1_user,
            employee_id="DOC001",
        )

        # Doctor 2 (unassigned)
        cls.doc2_user = User.objects.create_user("doc2_user", password="password")
        cls.doc2_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc2_profile = StaffProfile.objects.create(
            user=cls.doc2_user,
            employee_id="DOC002",
        )

        # Reception
        cls.reception_user = User.objects.create_user("reception_user", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC001",
        )

        # Patients
        cls.patient = Patient.objects.create(
            mrn="PAT-000101",
            full_name="George Patient",
            allergy_safety_notes="Latex allergy",
        )
        cls.visit_type = VisitType.objects.create(name="Consultation", code="CONS")

        # In-progress appointment for Doctor 1
        cls.appointment_in_progress = Appointment.objects.create(
            patient=cls.patient,
            doctor=cls.doc1_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
            status=Appointment.Status.IN_PROGRESS,
            started_at=timezone.now(),
        )

        # Scheduled appointment (not yet started)
        cls.appointment_scheduled = Appointment.objects.create(
            patient=cls.patient,
            doctor=cls.doc1_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now() + timedelta(hours=1),
            status=Appointment.Status.SCHEDULED,
        )

        # Medicine for prescription formset
        cls.medicine = Medicine.objects.create(
            code="MED001",
            generic_name="Amoxicillin",
            brand_name="Mox 500",
            dosage_form="Capsule",
            strength="500mg",
            unit="strip",
        )

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(
            f"/consultations/appointment/{self.appointment_in_progress.pk}/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertRedirects(
            response,
            f"/accounts/login/?next=/consultations/appointment/{self.appointment_in_progress.pk}/",
            fetch_redirect_response=False,
        )

    def test_reception_cannot_access_consultation_endpoints(self):
        self.client.force_login(self.reception_user)
        # Cannot access consultation form
        res_create = self.client.get(
            f"/consultations/appointment/{self.appointment_in_progress.pk}/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_create.status_code, 403)

        # Cannot access clinical history
        res_hist = self.client.get(
            f"/clinical/patients/{self.patient.pk}/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_hist.status_code, 403)

    def test_consultation_form_requires_in_progress_status(self):
        self.client.force_login(self.doc1_user)
        # Attempt to open consultation for an appointment that is only SCHEDULED
        response = self.client.get(
            f"/consultations/appointment/{self.appointment_scheduled.pk}/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 404)

    def test_unassigned_doctor_cannot_open_consultation(self):
        self.client.force_login(self.doc2_user)
        # Doctor 2 attempting to open Doctor 1's appointment
        response = self.client.get(
            f"/consultations/appointment/{self.appointment_in_progress.pk}/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 404)

        # Doctor 2 attempting direct POST
        post_response = self.client.post(
            f"/consultations/appointment/{self.appointment_in_progress.pk}/",
            {
                "clinical_notes": "Unauthorized note",
                "diagnosis": "Unauthorized diagnosis",
                "items-TOTAL_FORMS": "0",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(post_response.status_code, 404)

    def test_attending_doctor_creates_consultation_and_emits_audit(self):
        self.client.force_login(self.doc1_user)
        response = self.client.post(
            f"/consultations/appointment/{self.appointment_in_progress.pk}/",
            {
                "clinical_notes": "Patient presents with seasonal fever and sore throat.",
                "diagnosis": "Acute Pharyngitis",
                "follow_up_note": "Review in 3 days if fever persists.",
                "items-TOTAL_FORMS": "0",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        consultation = Consultation.objects.get(appointment=self.appointment_in_progress)
        self.assertEqual(consultation.doctor, self.doc1_profile)
        self.assertEqual(consultation.patient, self.patient)
        self.assertEqual(consultation.diagnosis, "Acute Pharyngitis")

        # Verify audit log
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.consultation_created",
                target_id=str(consultation.pk),
            ).exists()
        )

    def test_repeated_or_concurrent_submission_prevents_duplicate_consultation(self):
        self.client.force_login(self.doc1_user)
        # First submission creates consultation
        consultation = Consultation.objects.create(
            appointment=self.appointment_in_progress,
            patient=self.patient,
            doctor=self.doc1_profile,
            clinical_notes="First note",
            diagnosis="First diagnosis",
        )
        # Attempt second submission
        response = self.client.post(
            f"/consultations/appointment/{self.appointment_in_progress.pk}/",
            {
                "clinical_notes": "Second note",
                "diagnosis": "Second diagnosis",
                "items-TOTAL_FORMS": "0",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertRedirects(
            response,
            f"/consultations/{consultation.pk}/",
            fetch_redirect_response=False,
        )
        self.assertEqual(Consultation.objects.filter(appointment=self.appointment_in_progress).count(), 1)

    def test_consultation_detail_restricted_to_authoring_doctor(self):
        consultation = Consultation.objects.create(
            appointment=self.appointment_in_progress,
            patient=self.patient,
            doctor=self.doc1_profile,
            clinical_notes="Confidential clinical notes",
            diagnosis="Private diagnosis",
        )

        # Doctor 2 gets 404
        self.client.force_login(self.doc2_user)
        res_doc2 = self.client.get(f"/consultations/{consultation.pk}/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_doc2.status_code, 404)

        # Doctor 1 gets 200 and audit event is recorded
        self.client.force_login(self.doc1_user)
        res_doc1 = self.client.get(f"/consultations/{consultation.pk}/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_doc1.status_code, 200)
        self.assertContains(res_doc1, "Confidential clinical notes")
        self.assertContains(res_doc1, "Private diagnosis")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.consultation_viewed",
                target_id=str(consultation.pk),
            ).exists()
        )
