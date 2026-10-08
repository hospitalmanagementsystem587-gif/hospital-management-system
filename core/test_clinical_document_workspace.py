import hashlib
import io
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    AuditEvent,
    Patient,
    PatientDocument,
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
class ClinicalDocumentWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Doctor 1 (assigned to patient A)
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

        # Administrator
        cls.admin_user = User.objects.create_user("admin_user", password="password", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM001",
        )

        # Pharmacy
        cls.pharmacy_user = User.objects.create_user("pharmacy_user", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM001",
        )

        # Patient A (assigned to Doctor 1)
        cls.patient_a = Patient.objects.create(
            mrn="PAT-DOC-001",
            full_name="Alice Document Patient",
        )
        cls.visit_type = VisitType.objects.create(name="Consultation", code="CONS")
        Appointment.objects.create(
            patient=cls.patient_a,
            doctor=cls.doc1_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
            status=Appointment.Status.SCHEDULED,
        )

        # Patient B (not assigned to Doctor 1)
        cls.patient_b = Patient.objects.create(
            mrn="PAT-DOC-002",
            full_name="Bob Disjoint Patient",
        )

        # Clean document for Patient A
        clean_content = b"%PDF-1.4 synthetic pdf content for testing"
        cls.clean_doc = PatientDocument(
            patient=cls.patient_a,
            uploaded_by=cls.reception_profile,
            document_type=PatientDocument.DocumentType.LAB_REPORT,
            title="Blood Panel Results",
            content_type="application/pdf",
            size_bytes=len(clean_content),
            sha256=hashlib.sha256(clean_content).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.CLEAN,
        )
        cls.clean_doc.file.save("blood_test.pdf", ContentFile(clean_content), save=False)
        cls.clean_doc.save()

        # Rejected/Unclean document
        rejected_content = b"executable content"
        cls.rejected_doc = PatientDocument(
            patient=cls.patient_a,
            uploaded_by=cls.reception_profile,
            document_type=PatientDocument.DocumentType.OTHER,
            title="Malicious or Corrupted File",
            content_type="application/octet-stream",
            size_bytes=len(rejected_content),
            sha256=hashlib.sha256(rejected_content).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.REJECTED,
        )
        cls.rejected_doc.file.save("bad.exe", ContentFile(rejected_content), save=False)
        cls.rejected_doc.save()

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertRedirects(
            response,
            f"/accounts/login/?next=/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/",
            fetch_redirect_response=False,
        )

    def test_pharmacy_denied_document_access(self):
        self.client.force_login(self.pharmacy_user)
        # Cannot upload
        res_upload = self.client.post(
            f"/patients/{self.patient_a.pk}/documents/upload/",
            {"title": "Illicit Upload"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_upload.status_code, 403)

        # Cannot download
        res_dl = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_dl.status_code, 403)

    def test_authoring_or_assigned_doctor_can_download_clean_document_with_audit(self):
        self.client.force_login(self.doc1_user)
        response = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="patient.document_downloaded",
                target_id=str(self.patient_a.pk),
            ).exists()
        )

    def test_unassigned_doctor_receives_404_on_download(self):
        self.client.force_login(self.doc2_user)
        response = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 404)

    def test_rejected_document_returns_404(self):
        self.client.force_login(self.doc1_user)
        response = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.rejected_doc.public_id}/download/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 404)

    def test_reception_and_admin_can_download_clean_documents(self):
        for user in (self.reception_user, self.admin_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(
                    f"/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/",
                    HTTP_HOST="staff.hms.test",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Content-Type"], "application/pdf")

    def test_reception_uploads_valid_document_with_audit(self):
        self.client.force_login(self.reception_user)
        valid_pdf = SimpleUploadedFile(
            "discharge_summary.pdf",
            b"%PDF-1.4 valid dummy test content",
            content_type="application/pdf",
        )
        response = self.client.post(
            f"/patients/{self.patient_a.pk}/documents/upload/",
            {
                "document_type": PatientDocument.DocumentType.DISCHARGE_SUMMARY,
                "title": "Discharge Summary Sheet",
                "file": valid_pdf,
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        uploaded = PatientDocument.objects.filter(title="Discharge Summary Sheet").first()
        self.assertIsNotNone(uploaded)
        self.assertEqual(uploaded.patient, self.patient_a)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="patient.document_uploaded",
                target_id=str(self.patient_a.pk),
            ).exists()
        )
