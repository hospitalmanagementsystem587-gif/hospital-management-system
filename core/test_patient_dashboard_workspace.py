import hashlib
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    Consultation,
    Invoice,
    Medicine,
    Patient,
    PatientAccount,
    PatientDocument,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    VisitType,
)

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
class PatientDashboardWorkspaceTests(TestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            username="patient_jane",
            email="jane@example.com",
            password="securepassword123",
            first_name="Jane",
            last_name="Doe",
        )
        self.patient = Patient.objects.create(
            mrn="MRN-JANE-001",
            full_name="Jane Doe",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 30),
            phone="9876543210",
            email="jane@example.com",
        )
        self.patient_account = PatientAccount.objects.create(
            user=self.patient_user,
            patient=self.patient,
            is_verified=True,
        )

        # Other patient
        self.other_user = User.objects.create_user(
            username="patient_bob",
            email="bob@example.com",
            password="securepassword123",
            first_name="Bob",
            last_name="Smith",
        )
        self.other_patient = Patient.objects.create(
            mrn="MRN-BOB-002",
            full_name="Bob Smith",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 40),
            phone="9876543211",
            email="bob@example.com",
        )
        self.other_account = PatientAccount.objects.create(
            user=self.other_user,
            patient=self.other_patient,
            is_verified=True,
        )

        # Doctor
        self.doctor_user = User.objects.create_user(
            username="dr_alice",
            email="alice@example.com",
            password="securepassword123",
            first_name="Alice",
            last_name="Doctor",
        )
        self.doctor = StaffProfile.objects.create(
            user=self.doctor_user,
            employee_id="DOC-ALICE-01",
            job_title="Cardiologist",
            consultation_fee=500,
        )

        self.visit_type = VisitType.objects.create(
            name="General Consultation",
            code="GEN-OPD",
        )

        # Data for Jane
        self.apt_jane = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            visit_type=self.visit_type,
            scheduled_at=timezone.now() + timedelta(days=2),
            status=Appointment.Status.SCHEDULED,
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment=self.apt_jane,
            clinical_notes="Follow-up needed",
        )
        self.prescription = Prescription.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            consultation=self.consultation,
            number="RX-JANE-001",
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )
        self.med = Medicine.objects.create(
            code="MED-PCM",
            generic_name="Paracetamol",
            brand_name="Calpol 500mg",
            unit="tablet",
            is_active=True,
        )
        self.prescription_item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.med,
            dosage="500mg",
            frequency="TID",
            duration="5 days",
            quantity=10,
        )
        clean_content = b"%PDF-1.4 test report content"
        self.document = PatientDocument(
            patient=self.patient,
            uploaded_by=self.doctor,
            document_type=PatientDocument.DocumentType.LAB_REPORT,
            title="Blood Test Results",
            content_type="application/pdf",
            size_bytes=len(clean_content),
            sha256=hashlib.sha256(clean_content).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.CLEAN,
        )
        self.document.file.save("jane_report.pdf", ContentFile(clean_content), save=False)
        self.document.save()

        self.invoice = Invoice.objects.create(
            patient=self.patient,
            number="INV-JANE-001",
            total=150.00,
            status=Invoice.Status.ISSUED,
            issued_at=timezone.now(),
        )

        # Data for Bob
        self.apt_bob = Appointment.objects.create(
            patient=self.other_patient,
            doctor=self.doctor,
            visit_type=self.visit_type,
            scheduled_at=timezone.now() + timedelta(days=3),
            status=Appointment.Status.SCHEDULED,
        )
        self.prescription_bob = Prescription.objects.create(
            patient=self.other_patient,
            doctor=self.doctor,
            number="RX-BOB-002",
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )
        bob_content = b"%PDF-1.4 bob content"
        self.document_bob = PatientDocument(
            patient=self.other_patient,
            uploaded_by=self.doctor,
            document_type=PatientDocument.DocumentType.DISCHARGE_SUMMARY,
            title="Bob Discharge",
            content_type="application/pdf",
            size_bytes=len(bob_content),
            sha256=hashlib.sha256(bob_content).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.CLEAN,
        )
        self.document_bob.file.save("bob_report.pdf", ContentFile(bob_content), save=False)
        self.document_bob.save()

        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_unverified_patient_redirects_to_login(self):
        self.patient_account.is_verified = False
        self.patient_account.save()
        self.client.force_login(self.patient_user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 403)

    def test_archived_patient_redirects_to_login(self):
        self.patient.archived_at = timezone.now()
        self.patient.save()
        self.client.force_login(self.patient_user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 403)

    def test_verified_patient_can_view_dashboard(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "MRN-JANE-001")
        self.assertContains(resp, "Jane Doe")
        self.assertContains(resp, "Blood Test Results")
        self.assertContains(resp, "Paracetamol")
        # Ensure Bob's private data is NOT on Jane's dashboard
        self.assertNotContains(resp, "MRN-BOB-002")
        self.assertNotContains(resp, "Bob Discharge")
        self.assertNotContains(resp, "RX-BOB-002")

    def test_patient_can_download_own_document(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get(f"/documents/{self.document.public_id}/download/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.getvalue(), b"%PDF-1.4 test report content")

    def test_patient_cannot_download_other_patient_document(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get(f"/documents/{self.document_bob.public_id}/download/")
        self.assertEqual(resp.status_code, 404)

    def test_patient_can_print_own_prescription(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get(f"/prescriptions/{self.prescription.id}/print/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Paracetamol")
        self.assertContains(resp, "Jane Doe")

    def test_patient_cannot_print_other_patient_prescription(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get(f"/prescriptions/{self.prescription_bob.id}/print/")
        self.assertEqual(resp.status_code, 404)
