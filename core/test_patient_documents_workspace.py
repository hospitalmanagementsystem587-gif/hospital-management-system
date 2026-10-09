import hashlib
from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Patient,
    PatientAccount,
    PatientDocument,
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
    ALLOWED_HOSTS=["testserver", ".hms.test"],
)
class PatientDocumentsWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Doctor / Staff Uploader
        cls.doc_user = User.objects.create_user("doc_uploader", password="password")
        cls.doc_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc_profile = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-DOCS-01",
        )

        # Patient 1: Alice (verified)
        cls.alice_user = User.objects.create_user(
            "alice_patient",
            email="alice@example.com",
            password="Password123!",
            first_name="Alice",
            last_name="Gupta",
        )
        cls.alice_patient = Patient.objects.create(
            mrn="MRN-ALICE-DOC-01",
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
            "bob_patient",
            email="bob@example.com",
            password="Password123!",
            first_name="Bob",
            last_name="Verma",
        )
        cls.bob_patient = Patient.objects.create(
            mrn="MRN-BOB-DOC-01",
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

        # Alice's released & clean lab report
        file_content_1 = b"%PDF-1.4 test blood report data"
        cls.alice_doc_released = PatientDocument.objects.create(
            patient=cls.alice_patient,
            title="Complete Blood Count",
            document_type=PatientDocument.DocumentType.LAB_REPORT,
            file=ContentFile(file_content_1, name="cbc_report.pdf"),
            content_type="application/pdf",
            size_bytes=len(file_content_1),
            sha256=hashlib.sha256(file_content_1).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.CLEAN,
            patient_released_at=timezone.now() - timedelta(days=2),
            uploaded_by=cls.doc_profile,
            notes="Routine blood work results",
        )

        # Alice's pending validation report (must NOT be visible or downloadable)
        file_content_2 = b"%PDF-1.4 pending scan report"
        cls.alice_doc_pending = PatientDocument.objects.create(
            patient=cls.alice_patient,
            title="Chest X-Ray Preliminary",
            document_type=PatientDocument.DocumentType.RADIOLOGY,
            file=ContentFile(file_content_2, name="cxr_prelim.pdf"),
            content_type="application/pdf",
            size_bytes=len(file_content_2),
            sha256=hashlib.sha256(file_content_2).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.PENDING,
            patient_released_at=None,
            uploaded_by=cls.doc_profile,
        )

        # Alice's unreleased clean report (must NOT be visible or downloadable)
        file_content_3 = b"%PDF-1.4 unreleased biopsy report"
        cls.alice_doc_unreleased = PatientDocument.objects.create(
            patient=cls.alice_patient,
            title="Biopsy Analysis Unreleased",
            document_type=PatientDocument.DocumentType.DISCHARGE_SUMMARY,
            file=ContentFile(file_content_3, name="biopsy.pdf"),
            content_type="application/pdf",
            size_bytes=len(file_content_3),
            sha256=hashlib.sha256(file_content_3).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.CLEAN,
            patient_released_at=None,
            uploaded_by=cls.doc_profile,
        )

        # Alice's revoked report (must NOT be visible or downloadable)
        file_content_4 = b"%PDF-1.4 revoked report"
        cls.alice_doc_revoked = PatientDocument.objects.create(
            patient=cls.alice_patient,
            title="Old Medical Record Revoked",
            document_type=PatientDocument.DocumentType.OTHER,
            file=ContentFile(file_content_4, name="revoked.pdf"),
            content_type="application/pdf",
            size_bytes=len(file_content_4),
            sha256=hashlib.sha256(file_content_4).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.CLEAN,
            patient_released_at=timezone.now() - timedelta(days=10),
            patient_access_revoked_at=timezone.now() - timedelta(days=1),
            uploaded_by=cls.doc_profile,
        )

        # Bob's released lab report
        file_content_bob = b"%PDF-1.4 bob blood report"
        cls.bob_doc_released = PatientDocument.objects.create(
            patient=cls.bob_patient,
            title="Bob Lipid Profile",
            document_type=PatientDocument.DocumentType.LAB_REPORT,
            file=ContentFile(file_content_bob, name="lipid_bob.pdf"),
            content_type="application/pdf",
            size_bytes=len(file_content_bob),
            sha256=hashlib.sha256(file_content_bob).hexdigest(),
            validation_status=PatientDocument.ValidationStatus.CLEAN,
            patient_released_at=timezone.now() - timedelta(days=1),
            uploaded_by=cls.doc_profile,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get("/documents/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

        resp_dl = self.client.get(f"/documents/{self.alice_doc_released.public_id}/download/")
        self.assertEqual(resp_dl.status_code, 302)
        self.assertIn("/accounts/login/", resp_dl.url)

    def test_unverified_patient_cannot_view_documents(self):
        self.alice_account.is_verified = False
        self.alice_account.save(update_fields=["is_verified"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/documents/")
        self.assertEqual(resp.status_code, 403)

    def test_archived_patient_cannot_view_documents(self):
        self.alice_patient.archived_at = timezone.now()
        self.alice_patient.save(update_fields=["archived_at"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/documents/")
        self.assertEqual(resp.status_code, 403)

    def test_documents_list_only_released_clean_and_unrevoked(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get("/documents/")
        self.assertEqual(resp.status_code, 200)

        # Alice's released clean report must be visible
        self.assertContains(resp, "Complete Blood Count")
        self.assertContains(resp, "Routine blood work results")

        # Pending, unreleased, revoked documents must NOT be visible
        self.assertNotContains(resp, "Chest X-Ray Preliminary")
        self.assertNotContains(resp, "Biopsy Analysis Unreleased")
        self.assertNotContains(resp, "Old Medical Record Revoked")

        # Bob's documents must NOT leak
        self.assertNotContains(resp, "Bob Lipid Profile")

    def test_document_category_and_search_filter(self):
        self.client.force_login(self.alice_user)

        # Filter by matching category
        resp = self.client.get(f"/documents/?type={PatientDocument.DocumentType.LAB_REPORT}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Complete Blood Count")

        # Filter by non-matching category
        resp_no_match = self.client.get(f"/documents/?type={PatientDocument.DocumentType.RADIOLOGY}")
        self.assertEqual(resp_no_match.status_code, 200)
        self.assertNotContains(resp_no_match, "Complete Blood Count")
        self.assertContains(resp_no_match, "No clinical documents found")

        # Search by query match
        resp_q = self.client.get("/documents/?q=Blood")
        self.assertEqual(resp_q.status_code, 200)
        self.assertContains(resp_q, "Complete Blood Count")

        # Search by non-matching query
        resp_q_none = self.client.get("/documents/?q=CardiologyXYZ")
        self.assertEqual(resp_q_none.status_code, 200)
        self.assertNotContains(resp_q_none, "Complete Blood Count")

    def test_document_download_success_and_headers(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get(f"/documents/{self.alice_doc_released.public_id}/download/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertEqual(resp["Cache-Control"], "private, no-store")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_cannot_download_unclean_document(self):
        self.client.force_login(self.alice_user)

        # Pending validation document returns 404
        resp_pending = self.client.get(f"/documents/{self.alice_doc_pending.public_id}/download/")
        self.assertEqual(resp_pending.status_code, 404)

    def test_cannot_download_unreleased_or_revoked_document(self):
        self.client.force_login(self.alice_user)
        unreleased = self.client.get(
            f"/documents/{self.alice_doc_unreleased.public_id}/download/"
        )
        revoked = self.client.get(
            f"/documents/{self.alice_doc_revoked.public_id}/download/"
        )
        self.assertEqual(unreleased.status_code, 404)
        self.assertEqual(revoked.status_code, 404)

    def test_cross_patient_download_returns_404(self):
        # Alice cannot download Bob's document
        self.client.force_login(self.alice_user)
        resp = self.client.get(f"/documents/{self.bob_doc_released.public_id}/download/")
        self.assertEqual(resp.status_code, 404)
