import hashlib
import shutil
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.forms import PatientDocumentForm
from core.models import (
    Appointment,
    Consultation,
    Department,
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


def clean_test_document_scanner(upload):
    return True


class PatientHealthRecordsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.private_directory = tempfile.mkdtemp(prefix="hms-private-documents-")
        self.storage = PatientDocument._meta.get_field("file").storage
        self.original_storage_location = self.storage._location
        self.storage._location = self.private_directory
        for cached_name in ("base_location", "location"):
            self.storage.__dict__.pop(cached_name, None)

        self.doctor_group = Group.objects.create(name="Doctor")
        self.reception_group = Group.objects.create(name="Reception")
        self.reception_group.permissions.add(
            Permission.objects.get(content_type__app_label="core", codename="view_patient")
        )
        self.department = Department.objects.create(code="API-CLIN", name="Medicine")
        self.doctor_user = User.objects.create_user(
            username="records-doctor",
            password="Synthetic-Password-123!",
            first_name="Synthetic",
            last_name="Doctor",
        )
        self.doctor_user.groups.add(self.doctor_group)
        self.doctor = StaffProfile.objects.create(
            user=self.doctor_user,
            employee_id="RECORDS-DOC-001",
            department=self.department,
        )
        self.reception_user = User.objects.create_user(
            username="records-reception",
            password="Synthetic-Password-123!",
        )
        self.reception_user.groups.add(self.reception_group)
        StaffProfile.objects.create(
            user=self.reception_user,
            employee_id="RECORDS-REC-001",
        )
        self.visit_type = VisitType.objects.create(
            code="RECORDS-VISIT", name="Consultation"
        )

        self.patient = Patient.objects.create(
            mrn="RECORDS-001", full_name="Synthetic Record Patient"
        )
        self.patient_user = User.objects.create_user(
            username="records-patient", password="Synthetic-Password-123!"
        )
        PatientAccount.objects.create(
            user=self.patient_user, patient=self.patient, is_verified=True
        )
        self.other_patient = Patient.objects.create(
            mrn="RECORDS-002", full_name="Other Synthetic Patient"
        )
        self.other_user = User.objects.create_user(
            username="other-records-patient", password="Synthetic-Password-123!"
        )
        PatientAccount.objects.create(
            user=self.other_user, patient=self.other_patient, is_verified=True
        )

        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            visit_type=self.visit_type,
            scheduled_at=timezone.now() - timedelta(days=1),
            completed_at=timezone.now() - timedelta(hours=23),
            status=Appointment.Status.COMPLETED,
        )
        released_at = timezone.now() - timedelta(hours=22)
        self.released_record = Consultation.objects.create(
            appointment=self.appointment,
            patient=self.patient,
            doctor=self.doctor,
            clinical_notes="Never expose this synthetic clinical note",
            diagnosis="Never expose this synthetic diagnosis",
            follow_up_date=timezone.localdate() + timedelta(days=14),
            follow_up_note="Return in two weeks if symptoms continue.",
            patient_released_at=released_at,
        )
        self.unreleased_record = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            clinical_notes="Unreleased private note",
            diagnosis="Unreleased private diagnosis",
        )
        self.revoked_record = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            follow_up_note="Revoked follow-up",
            patient_released_at=released_at,
            patient_access_revoked_at=timezone.now(),
        )
        self.other_record = Consultation.objects.create(
            patient=self.other_patient,
            doctor=self.doctor,
            patient_released_at=released_at,
        )

        self.medicine = Medicine.objects.create(
            code="RECORDS-MED-001",
            generic_name="Synthetic medicine",
            brand_name="Synthetic brand",
            strength="10 mg",
            dosage_form="tablet",
            unit="tablet",
        )
        self.issued_prescription = Prescription.objects.create(
            number="RECORDS-RX-001",
            consultation=self.released_record,
            patient=self.patient,
            doctor=self.doctor,
            status=Prescription.Status.ISSUED,
            issued_at=released_at,
        )
        PrescriptionItem.objects.create(
            prescription=self.issued_prescription,
            medicine=self.medicine,
            dosage="1 tablet",
            frequency="twice daily",
            duration="5 days",
            instructions="After food",
            quantity=Decimal("10"),
        )
        self.draft_prescription = Prescription.objects.create(
            number="RECORDS-RX-DRAFT",
            patient=self.patient,
            doctor=self.doctor,
            status=Prescription.Status.DRAFT,
        )
        self.cancelled_prescription = Prescription.objects.create(
            number="RECORDS-RX-CANCELLED",
            patient=self.patient,
            doctor=self.doctor,
            status=Prescription.Status.CANCELLED,
            issued_at=released_at,
        )
        self.unissued_prescription = Prescription.objects.create(
            number="RECORDS-RX-NO-DATE",
            patient=self.patient,
            doctor=self.doctor,
            status=Prescription.Status.ISSUED,
        )
        self.other_prescription = Prescription.objects.create(
            number="RECORDS-RX-OTHER",
            patient=self.other_patient,
            doctor=self.doctor,
            status=Prescription.Status.ISSUED,
            issued_at=released_at,
        )

        self.released_document = self._create_document(
            self.patient, "Released report", released_at=released_at
        )
        self.unreleased_document = self._create_document(
            self.patient, "Unreleased report"
        )
        self.revoked_document = self._create_document(
            self.patient,
            "Revoked report",
            released_at=released_at,
            revoked_at=timezone.now(),
        )
        self.pending_document = self._create_document(
            self.patient,
            "Pending scan",
            validation_status=PatientDocument.ValidationStatus.PENDING,
        )
        self.other_document = self._create_document(
            self.other_patient, "Other patient's report", released_at=released_at
        )

    def tearDown(self):
        self.storage._location = self.original_storage_location
        for cached_name in ("base_location", "location"):
            self.storage.__dict__.pop(cached_name, None)
        shutil.rmtree(self.private_directory, ignore_errors=True)

    def _auth(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _create_document(
        self,
        patient,
        title,
        *,
        released_at=None,
        revoked_at=None,
        validation_status=PatientDocument.ValidationStatus.CLEAN,
    ):
        content = f"%PDF-1.4 synthetic {title}".encode()
        document = PatientDocument(
            patient=patient,
            document_type=PatientDocument.DocumentType.LAB_REPORT,
            title=title,
            content_type="application/pdf",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            validation_status=validation_status,
            patient_released_at=released_at,
            patient_access_revoked_at=revoked_at,
        )
        document.file.save(f"{uuid.uuid4()}.pdf", ContentFile(content), save=False)
        document.save()
        return document

    def test_clinical_endpoints_require_verified_current_patient_account(self):
        endpoints = [
            "/api/v1/me/health-records/",
            "/api/v1/me/prescriptions/",
            "/api/v1/me/documents/",
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint, kind="anonymous"):
                self.client.credentials()
                self.assertEqual(
                    self.client.get(endpoint).status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )
            with self.subTest(endpoint=endpoint, kind="staff"):
                self._auth(self.reception_user)
                self.assertEqual(
                    self.client.get(endpoint).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        unverified_patient = Patient.objects.create(
            mrn="RECORDS-UNVERIFIED", full_name="Unverified Synthetic Patient"
        )
        unverified_user = User.objects.create_user(username="unverified-records")
        PatientAccount.objects.create(
            user=unverified_user, patient=unverified_patient, is_verified=False
        )
        self._auth(unverified_user)
        self.assertEqual(
            self.client.get(endpoints[0]).status_code, status.HTTP_403_FORBIDDEN
        )

        self.patient.archived_at = timezone.now()
        self.patient.save(update_fields=["archived_at"])
        self._auth(self.patient_user)
        self.assertEqual(
            self.client.get(endpoints[0]).status_code, status.HTTP_403_FORBIDDEN
        )

        unlinked_user = User.objects.create_user(username="unlinked-records")
        self._auth(unlinked_user)
        self.assertEqual(
            self.client.get(endpoints[0]).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_health_records_are_release_scoped_and_minimal(self):
        self._auth(self.patient_user)
        response = self.client.get("/api/v1/me/health-records/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.released_record.id)
        self.assertEqual(
            set(response.data[0]),
            {
                "id",
                "appointment_id",
                "doctor",
                "encounter_at",
                "released_at",
                "follow_up_date",
            },
        )
        self.assertNotIn("clinical_notes", str(response.data))
        self.assertNotIn("diagnosis", str(response.data))
        self.assertNotIn("follow_up_note", response.data[0])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", response["Vary"])

        detail = self.client.get(
            f"/api/v1/me/health-records/{self.released_record.id}/"
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            detail.data["follow_up_note"],
            "Return in two weeks if symptoms continue.",
        )
        self.assertEqual(
            detail.data["prescription_ids"], [self.issued_prescription.id]
        )
        self.assertNotIn("clinical_notes", detail.data)
        self.assertNotIn("diagnosis", detail.data)

        for hidden_record in (
            self.unreleased_record,
            self.revoked_record,
            self.other_record,
        ):
            with self.subTest(hidden_record=hidden_record.id):
                hidden = self.client.get(
                    f"/api/v1/me/health-records/{hidden_record.id}/"
                )
                self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_prescriptions_expose_only_issued_structured_content(self):
        self._auth(self.patient_user)
        response = self.client.get("/api/v1/me/prescriptions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        summary = response.data[0]
        self.assertEqual(summary["id"], self.issued_prescription.id)
        self.assertEqual(
            set(summary),
            {
                "id",
                "number",
                "consultation_id",
                "doctor",
                "issued_at",
                "item_count",
            },
        )
        self.assertNotIn("items", summary)

        detail = self.client.get(
            f"/api/v1/me/prescriptions/{self.issued_prescription.id}/"
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.data["items"]), 1)
        item = detail.data["items"][0]
        self.assertEqual(item["dosage"], "1 tablet")
        self.assertEqual(item["medicine"]["generic_name"], "Synthetic medicine")
        serialized = str(detail.data)
        for forbidden in (
            "clinical_notes",
            "diagnosis",
            "batch",
            "stock",
            "cost",
            "dispensing",
        ):
            self.assertNotIn(forbidden, serialized)

        for hidden_prescription in (
            self.draft_prescription,
            self.cancelled_prescription,
            self.unissued_prescription,
            self.other_prescription,
        ):
            with self.subTest(hidden_prescription=hidden_prescription.id):
                hidden = self.client.get(
                    f"/api/v1/me/prescriptions/{hidden_prescription.id}/"
                )
                self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_document_metadata_and_download_are_authorized_and_non_guessable(self):
        self._auth(self.patient_user)
        response = self.client.get("/api/v1/me/documents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        metadata = response.data[0]
        self.assertEqual(str(metadata["id"]), str(self.released_document.public_id))
        self.assertEqual(
            set(metadata),
            {
                "id",
                "document_type",
                "document_type_label",
                "title",
                "created_at",
                "content_type",
                "size_bytes",
                "download_url",
            },
        )
        self.assertEqual(
            metadata["download_url"],
            f"/api/v1/me/documents/{self.released_document.public_id}/download/",
        )
        self.assertNotIn("file", metadata)
        self.assertNotIn(self.released_document.file.name, str(metadata))
        self.assertNotIn("notes", metadata)
        self.assertNotIn("uploaded_by", metadata)

        download = self.client.get(metadata["download_url"])
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        self.assertEqual(download["Content-Type"], "application/pdf")
        self.assertEqual(download["Content-Length"], str(self.released_document.size_bytes))
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertEqual(download["Pragma"], "no-cache")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment;", download["Content-Disposition"])
        self.assertIn(str(self.released_document.public_id), download["Content-Disposition"])
        self.assertEqual(
            b"".join(download.streaming_content),
            b"%PDF-1.4 synthetic Released report",
        )

        hidden_responses = []
        for document in (
            self.unreleased_document,
            self.revoked_document,
            self.pending_document,
            self.other_document,
        ):
            hidden_responses.append(
                self.client.get(
                    f"/api/v1/me/documents/{document.public_id}/download/"
                )
            )
        hidden_responses.append(
            self.client.get(f"/api/v1/me/documents/{uuid.uuid4()}/download/")
        )
        for hidden in hidden_responses:
            self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(hidden.data, hidden_responses[0].data)

    def test_document_authorization_is_rechecked_and_tampering_fails_closed(self):
        self._auth(self.patient_user)
        download_url = (
            f"/api/v1/me/documents/{self.released_document.public_id}/download/"
        )
        self.released_document.patient_access_revoked_at = timezone.now()
        self.released_document.save(update_fields=["patient_access_revoked_at"])
        self.assertEqual(
            self.client.get(download_url).status_code, status.HTTP_404_NOT_FOUND
        )

        self.released_document.patient_access_revoked_at = None
        self.released_document.save(update_fields=["patient_access_revoked_at"])
        with self.released_document.file.storage.open(
            self.released_document.file.name, "wb"
        ) as tampered_file:
            tampered_file.write(b"%PDF-1.4 tampered")
        self.assertEqual(
            self.client.get(download_url).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_public_media_route_cannot_bypass_document_authorization(self):
        direct_url = f"/media/{self.released_document.file.name}"
        self.assertEqual(self.client.get(direct_url).status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(PATIENT_DOCUMENT_MAX_BYTES=128)
    def test_upload_validation_rejects_oversized_mislabeled_and_test_malware(self):
        invalid_uploads = (
            SimpleUploadedFile("large.pdf", b"%PDF-" + b"x" * 124),
            SimpleUploadedFile("mislabeled.png", b"%PDF-1.4 valid shape"),
            SimpleUploadedFile(
                "eicar.pdf",
                b"%PDF-1.4 EICAR-STANDARD-ANTIVIRUS-TEST-FILE",
            ),
        )
        for upload in invalid_uploads:
            with self.subTest(upload=upload.name):
                form = PatientDocumentForm(
                    data={"document_type": "lab_report", "title": "Invalid"},
                    files={"file": upload},
                )
                self.assertFalse(form.is_valid())
                self.assertIn("file", form.errors)

    def test_valid_upload_is_pending_without_configured_malware_scanner(self):
        upload = SimpleUploadedFile(
            "synthetic.pdf", b"%PDF-1.4 valid synthetic report"
        )
        form = PatientDocumentForm(
            data={"document_type": "lab_report", "title": "Valid synthetic report"},
            files={"file": upload},
        )

        self.assertTrue(form.is_valid(), form.errors)
        document = form.save(commit=False)
        self.assertEqual(document.content_type, "application/pdf")
        self.assertGreater(document.size_bytes, 0)
        self.assertEqual(len(document.sha256), 64)
        self.assertEqual(
            document.validation_status, PatientDocument.ValidationStatus.PENDING
        )

    @override_settings(
        PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK=(
            "core.test_patient_health_records_api.clean_test_document_scanner"
        )
    )
    def test_configured_clean_scanner_marks_valid_upload_clean(self):
        upload = SimpleUploadedFile(
            "synthetic.pdf", b"%PDF-1.4 scanner-approved synthetic report"
        )
        form = PatientDocumentForm(
            data={"document_type": "lab_report", "title": "Scanned synthetic report"},
            files={"file": upload},
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.save(commit=False).validation_status,
            PatientDocument.ValidationStatus.CLEAN,
        )

    def test_staff_download_uses_protected_route_and_existing_patient_scope(self):
        self.client.credentials()
        self.client.force_login(self.reception_user)
        response = self.client.get(
            reverse(
                "staff_patient_document_download",
                args=[self.patient.id, self.released_document.public_id],
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(
            b"".join(response.streaming_content),
            b"%PDF-1.4 synthetic Released report",
        )
