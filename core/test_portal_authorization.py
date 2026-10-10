import hashlib
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from core.authorization import (
    get_authorized_appointment_queryset,
    get_authorized_patient_queryset,
    user_can_access_portal,
)
from core.models import (
    Admission,
    Appointment,
    Bed,
    Consultation,
    Department,
    Invoice,
    Patient,
    PatientAccount,
    PatientDocument,
    PaymentMethod,
    Prescription,
    Service,
    StaffProfile,
    VisitType,
    Ward,
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
class PortalAwareAdmissionTests(TestCase):
    """Positive and negative tests for coarse portal admission across all 5 portal hosts."""

    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)

        cls.superuser = User.objects.create_superuser(
            username="super_user", email="super@hms.test", password="Password123!"
        )
        cls.admin_user = User.objects.create_user(
            username="admin_user", email="admin@hms.test", password="Password123!", is_staff=True
        )
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        StaffProfile.objects.create(user=cls.admin_user, employee_id="ADM-001")

        cls.doctor_user = User.objects.create_user(
            username="doc_user", email="doc@hms.test", password="Password123!"
        )
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        StaffProfile.objects.create(user=cls.doctor_user, employee_id="DOC-001")

        cls.reception_user = User.objects.create_user(
            username="rec_user", email="rec@hms.test", password="Password123!"
        )
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(user=cls.reception_user, employee_id="REC-001")

        cls.pharmacy_user = User.objects.create_user(
            username="pharm_user", email="pharm@hms.test", password="Password123!"
        )
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        StaffProfile.objects.create(user=cls.pharmacy_user, employee_id="PHARM-001")

        cls.verified_patient_user = User.objects.create_user(
            username="patient_v", email="v@hms.test", password="Password123!"
        )
        cls.patient_v = Patient.objects.create(mrn="PAT-V-001", full_name="Verified Patient")
        PatientAccount.objects.create(
            user=cls.verified_patient_user, patient=cls.patient_v, is_verified=True
        )

        cls.unverified_patient_user = User.objects.create_user(
            username="patient_unv", email="unv@hms.test", password="Password123!"
        )
        cls.patient_unv = Patient.objects.create(mrn="PAT-UNV-001", full_name="Unverified Patient")
        PatientAccount.objects.create(
            user=cls.unverified_patient_user, patient=cls.patient_unv, is_verified=False
        )

        cls.archived_patient_user = User.objects.create_user(
            username="patient_arch", email="arch@hms.test", password="Password123!"
        )
        cls.patient_arch = Patient.objects.create(
            mrn="PAT-ARCH-001", full_name="Archived Patient", archived_at=timezone.now()
        )
        PatientAccount.objects.create(
            user=cls.archived_patient_user, patient=cls.patient_arch, is_verified=True
        )

        cls.inactive_user = User.objects.create_user(
            username="inactive_doc", email="inact@hms.test", password="Password123!", is_active=False
        )
        cls.inactive_user.groups.add(Group.objects.get(name="Doctor"))

        cls.ordinary_user = User.objects.create_user(
            username="ordinary_user", email="ord@hms.test", password="Password123!"
        )

        # Dual-role user: Has a verified patient account AND is also a Receptionist
        cls.dual_role_user = User.objects.create_user(
            username="dual_role", email="dual@hms.test", password="Password123!"
        )
        cls.dual_role_user.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(user=cls.dual_role_user, employee_id="DUAL-001")
        cls.dual_patient = Patient.objects.create(mrn="PAT-DUAL-001", full_name="Dual Role Patient")
        PatientAccount.objects.create(
            user=cls.dual_role_user, patient=cls.dual_patient, is_verified=True
        )

    def setUp(self):
        cache.clear()

    def test_anonymous_access_redirects_to_login_on_all_portals(self):
        hosts = [
            "admin.hms.test",
            "staff.hms.test",
            "store.hms.test",
            "patient.hms.test",
            "agent.hms.test",
        ]
        for host in hosts:
            with self.subTest(host=host):
                response = self.client.get("/", HTTP_HOST=host)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/?next=/", response.url)

    def test_inactive_user_rejected_on_all_portals(self):
        for portal in ("admin", "staff", "store", "patient", "agent"):
            self.assertFalse(user_can_access_portal(self.inactive_user, portal))

        # Inactive users cannot authenticate; attempting login fails and unauthenticated portal requests redirect to login
        for host in (
            "admin.hms.test",
            "staff.hms.test",
            "store.hms.test",
            "patient.hms.test",
            "agent.hms.test",
        ):
            with self.subTest(host=host):
                cache.clear()
                client = Client()
                res_login = client.post(
                    "/accounts/login/",
                    {"username": self.inactive_user.username, "password": "Password123!"},
                    HTTP_HOST=host,
                )
                self.assertEqual(res_login.status_code, 200)
                self.assertNotIn("_auth_user_id", client.session)

                # Accessing portal without valid session redirects to login
                res_req = client.get("/", HTTP_HOST=host)
                self.assertEqual(res_req.status_code, 302)
                self.assertIn("/accounts/login/?next=/", res_req.url)

    def test_admin_portal_admission(self):
        # Superuser and staff admin allowed
        self.assertTrue(user_can_access_portal(self.superuser, "admin"))
        self.assertTrue(user_can_access_portal(self.admin_user, "admin"))

        # Non-staff or non-admin roles rejected
        self.assertFalse(user_can_access_portal(self.doctor_user, "admin"))
        self.assertFalse(user_can_access_portal(self.reception_user, "admin"))
        self.assertFalse(user_can_access_portal(self.pharmacy_user, "admin"))
        self.assertFalse(user_can_access_portal(self.verified_patient_user, "admin"))
        self.assertFalse(user_can_access_portal(self.ordinary_user, "admin"))

        self.client.force_login(self.admin_user)
        self.assertRedirects(
            self.client.get("/", HTTP_HOST="admin.hms.test"),
            "/admin/",
            fetch_redirect_response=False,
        )

        self.client.force_login(self.doctor_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="admin.hms.test").status_code, 403)

    def test_staff_portal_admission(self):
        # Staff roles allowed
        for user in (self.superuser, self.admin_user, self.doctor_user, self.reception_user, self.pharmacy_user):
            with self.subTest(user=user.username):
                self.assertTrue(user_can_access_portal(user, "staff"))

        # Patient and ordinary user rejected
        self.assertFalse(user_can_access_portal(self.verified_patient_user, "staff"))
        self.assertFalse(user_can_access_portal(self.ordinary_user, "staff"))

        self.client.force_login(self.doctor_user)
        self.assertEqual(self.client.get("/__portal__/", HTTP_HOST="staff.hms.test").status_code, 200)

        self.client.force_login(self.verified_patient_user)
        self.assertEqual(self.client.get("/__portal__/", HTTP_HOST="staff.hms.test").status_code, 403)

    def test_store_portal_admission(self):
        # Administrator and Pharmacy allowed
        self.assertTrue(user_can_access_portal(self.superuser, "store"))
        self.assertTrue(user_can_access_portal(self.admin_user, "store"))
        self.assertTrue(user_can_access_portal(self.pharmacy_user, "store"))

        # Doctor, Reception, Patient, Ordinary rejected
        self.assertFalse(user_can_access_portal(self.doctor_user, "store"))
        self.assertFalse(user_can_access_portal(self.reception_user, "store"))
        self.assertFalse(user_can_access_portal(self.verified_patient_user, "store"))
        self.assertFalse(user_can_access_portal(self.ordinary_user, "store"))

        self.client.force_login(self.pharmacy_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="store.hms.test").status_code, 200)

        self.client.force_login(self.doctor_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="store.hms.test").status_code, 403)

    def test_patient_portal_admission(self):
        # Verified patient allowed
        self.assertTrue(user_can_access_portal(self.verified_patient_user, "patient"))

        # Unverified patient rejected
        self.assertFalse(user_can_access_portal(self.unverified_patient_user, "patient"))

        # Archived patient rejected
        self.assertFalse(user_can_access_portal(self.archived_patient_user, "patient"))

        # Staff users without verified patient accounts rejected
        self.assertFalse(user_can_access_portal(self.doctor_user, "patient"))
        self.assertFalse(user_can_access_portal(self.reception_user, "patient"))
        self.assertFalse(user_can_access_portal(self.ordinary_user, "patient"))

        # Superuser allowed
        self.assertTrue(user_can_access_portal(self.superuser, "patient"))

        self.client.force_login(self.verified_patient_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="patient.hms.test").status_code, 200)

        self.client.force_login(self.unverified_patient_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="patient.hms.test").status_code, 403)

        self.client.force_login(self.archived_patient_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="patient.hms.test").status_code, 403)

        self.client.force_login(self.doctor_user)
        self.assertEqual(self.client.get("/", HTTP_HOST="patient.hms.test").status_code, 403)

    def test_dual_role_user_portal_access(self):
        # Dual-role user (verified patient + Receptionist) can access both patient and staff portals
        self.assertTrue(user_can_access_portal(self.dual_role_user, "patient"))
        self.assertTrue(user_can_access_portal(self.dual_role_user, "staff"))
        # But cannot access admin or store
        self.assertFalse(user_can_access_portal(self.dual_role_user, "admin"))
        self.assertFalse(user_can_access_portal(self.dual_role_user, "store"))

    def test_agent_portal_fails_closed(self):
        # Fails closed to only superuser and Administrator
        self.assertTrue(user_can_access_portal(self.superuser, "agent"))
        self.assertTrue(user_can_access_portal(self.admin_user, "agent"))

        for user in (
            self.doctor_user,
            self.reception_user,
            self.pharmacy_user,
            self.verified_patient_user,
            self.ordinary_user,
        ):
            with self.subTest(user=user.username):
                self.assertFalse(user_can_access_portal(user, "agent"))
                self.client.force_login(user)
                self.assertEqual(self.client.get("/", HTTP_HOST="agent.hms.test").status_code, 403)


class ObjectLevelAuthorizationTests(TestCase):
    """Rigorous object and resource-level authorization tests across models and views."""

    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)

        # Department and VisitType
        cls.dept = Department.objects.create(code="GEN", name="General Medicine")
        cls.visit_type = VisitType.objects.create(code="OPD", name="OPD Consultation")
        cls.service = Service.objects.create(
            code="CONSULT", name="Doctor Consultation", current_charge=Decimal("500.00"), is_active=True
        )
        cls.payment_method = PaymentMethod.objects.create(code="CASH", name="Cash", is_active=True)

        # Staff users
        cls.admin_user = User.objects.create_user("admin_obj", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user, employee_id="ADM-OBJ-01", department=cls.dept
        )

        cls.reception_user = User.objects.create_user("rec_obj")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user, employee_id="REC-OBJ-01", department=cls.dept
        )

        cls.doc1_user = User.objects.create_user("doc1_obj")
        cls.doc1_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc1_profile = StaffProfile.objects.create(
            user=cls.doc1_user, employee_id="DOC1-OBJ-01", department=cls.dept
        )

        cls.doc2_user = User.objects.create_user("doc2_obj")
        cls.doc2_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc2_profile = StaffProfile.objects.create(
            user=cls.doc2_user, employee_id="DOC2-OBJ-01", department=cls.dept
        )

        cls.pharm_user = User.objects.create_user("pharm_obj")
        cls.pharm_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharm_profile = StaffProfile.objects.create(
            user=cls.pharm_user, employee_id="PHARM-OBJ-01", department=cls.dept
        )

        cls.ordinary_user = User.objects.create_user("ordinary_obj")

        # Patients
        cls.patient_a = Patient.objects.create(mrn="PAT-A", full_name="Patient Alice")
        cls.patient_b = Patient.objects.create(mrn="PAT-B", full_name="Patient Bob")
        cls.archived_patient = Patient.objects.create(
            mrn="PAT-ARCH", full_name="Archived Person", archived_at=timezone.now()
        )

        # Appointments
        cls.apt_doc1 = Appointment.objects.create(
            patient=cls.patient_a,
            doctor=cls.doc1_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
            status=Appointment.Status.SCHEDULED,
        )
        cls.apt_doc2 = Appointment.objects.create(
            patient=cls.patient_b,
            doctor=cls.doc2_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
            status=Appointment.Status.SCHEDULED,
        )

        # Consultations
        cls.consult_doc1 = Consultation.objects.create(
            appointment=cls.apt_doc1,
            patient=cls.patient_a,
            doctor=cls.doc1_profile,
            clinical_notes="Mild headache",
            diagnosis="Tension headache",
        )

        # Prescriptions
        cls.presc_doc1 = Prescription.objects.create(
            number="RX-001",
            consultation=cls.consult_doc1,
            patient=cls.patient_a,
            doctor=cls.doc1_profile,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )

        # Inpatient setup
        cls.ward = Ward.objects.create(name="General Ward", code="GW", category=Ward.Category.GENERAL)
        cls.bed = Bed.objects.create(ward=cls.ward, bed_number="GW-101", status=Bed.Status.AVAILABLE)
        cls.admission = Admission.objects.create(
            admission_number="ADM-2026-001",
            patient=cls.patient_a,
            bed=cls.bed,
            admitting_doctor=cls.doc1_profile,
            admitted_by=cls.reception_profile,
            status=Admission.Status.ADMITTED,
        )

        # Documents
        def _make_doc(patient, title, val_status, released_at=None, revoked_at=None):
            content = f"%PDF-1.4 test document content {title}".encode()
            doc = PatientDocument(
                patient=patient,
                uploaded_by=cls.reception_profile,
                document_type=PatientDocument.DocumentType.LAB_REPORT,
                title=title,
                content_type="application/pdf",
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                validation_status=val_status,
                patient_released_at=released_at,
                patient_access_revoked_at=revoked_at,
            )
            doc.file.save(f"{title}.pdf", ContentFile(content), save=False)
            doc.save()
            return doc

        cls.clean_doc = _make_doc(
            cls.patient_a, "Blood Test", PatientDocument.ValidationStatus.CLEAN, released_at=timezone.now()
        )
        cls.unreleased_doc = _make_doc(
            cls.patient_a, "Internal Staff Note", PatientDocument.ValidationStatus.CLEAN, released_at=None
        )
        cls.revoked_doc = _make_doc(
            cls.patient_a,
            "Revoked Scan",
            PatientDocument.ValidationStatus.CLEAN,
            released_at=timezone.now(),
            revoked_at=timezone.now(),
        )
        cls.rejected_doc = _make_doc(
            cls.patient_a, "Quarantined File", PatientDocument.ValidationStatus.REJECTED, released_at=None
        )

    def test_patient_read_queryset_isolation(self):
        # Reception sees all active patients
        rec_patients = get_authorized_patient_queryset(self.reception_user)
        self.assertIn(self.patient_a, rec_patients)
        self.assertIn(self.patient_b, rec_patients)
        self.assertNotIn(self.archived_patient, rec_patients)

        # Doctor 1 only sees Patient A (assigned via appointment)
        doc1_patients = get_authorized_patient_queryset(self.doc1_user)
        self.assertIn(self.patient_a, doc1_patients)
        self.assertNotIn(self.patient_b, doc1_patients)
        self.assertNotIn(self.archived_patient, doc1_patients)

        # Doctor 2 only sees Patient B
        doc2_patients = get_authorized_patient_queryset(self.doc2_user)
        self.assertNotIn(self.patient_a, doc2_patients)
        self.assertIn(self.patient_b, doc2_patients)

        # Ordinary user sees none
        self.assertEqual(get_authorized_patient_queryset(self.ordinary_user).count(), 0)

    def test_appointment_queryset_isolation(self):
        # Reception sees all appointments
        rec_apts = get_authorized_appointment_queryset(self.reception_user)
        self.assertIn(self.apt_doc1, rec_apts)
        self.assertIn(self.apt_doc2, rec_apts)

        # Doctor 1 only sees own appointments
        doc1_apts = get_authorized_appointment_queryset(self.doc1_user)
        self.assertIn(self.apt_doc1, doc1_apts)
        self.assertNotIn(self.apt_doc2, doc1_apts)

        # Doctor 2 only sees own appointments
        doc2_apts = get_authorized_appointment_queryset(self.doc2_user)
        self.assertNotIn(self.apt_doc1, doc2_apts)
        self.assertIn(self.apt_doc2, doc2_apts)

        # Ordinary user sees none
        self.assertEqual(get_authorized_appointment_queryset(self.ordinary_user).count(), 0)

    def test_live_patient_and_appointment_routes_use_centralized_scopes(self):
        self.client.force_login(self.reception_user)
        patient_response = self.client.get("/patients/")
        self.assertEqual(patient_response.status_code, 200)
        self.assertContains(patient_response, self.patient_a.full_name)
        self.assertContains(patient_response, self.patient_b.full_name)
        self.assertNotContains(patient_response, self.archived_patient.full_name)

        appointment_response = self.client.get("/appointments/")
        self.assertEqual(appointment_response.status_code, 200)
        self.assertContains(appointment_response, self.patient_a.full_name)
        self.assertContains(appointment_response, self.patient_b.full_name)

        self.client.force_login(self.doc1_user)
        doctor_patient_response = self.client.get("/patients/")
        self.assertEqual(doctor_patient_response.status_code, 200)
        self.assertContains(doctor_patient_response, self.patient_a.full_name)
        self.assertNotContains(doctor_patient_response, self.patient_b.full_name)

        doctor_appointment_response = self.client.get("/appointments/")
        self.assertEqual(doctor_appointment_response.status_code, 200)
        self.assertContains(doctor_appointment_response, self.patient_a.full_name)
        self.assertNotContains(doctor_appointment_response, self.patient_b.full_name)

        for user in (self.admin_user, self.pharm_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get("/patients/").status_code, 403)
                self.assertEqual(self.client.get("/appointments/").status_code, 403)

    def test_consultation_detail_isolation(self):
        # Doctor 1 can view own consultation
        self.client.force_login(self.doc1_user)
        response = self.client.get(f"/consultations/{self.consult_doc1.pk}/")
        self.assertEqual(response.status_code, 200)

        # Doctor 2 accessing Doctor 1's consultation receives non-disclosing 404
        self.client.force_login(self.doc2_user)
        response = self.client.get(f"/consultations/{self.consult_doc1.pk}/")
        self.assertEqual(response.status_code, 404)

        # Receptionist accessing clinical consultation gets 403 (no view_consultation perm)
        self.client.force_login(self.reception_user)
        response = self.client.get(f"/consultations/{self.consult_doc1.pk}/")
        self.assertEqual(response.status_code, 403)

    def test_prescription_print_isolation(self):
        # Doctor 1 (prescriber) can view
        self.client.force_login(self.doc1_user)
        response = self.client.get(f"/prescriptions/{self.presc_doc1.pk}/print/")
        self.assertEqual(response.status_code, 200)

        # Doctor 2 cannot view (non-disclosing 404)
        self.client.force_login(self.doc2_user)
        response = self.client.get(f"/prescriptions/{self.presc_doc1.pk}/print/")
        self.assertEqual(response.status_code, 404)

        # Pharmacy can view issued prescription
        self.client.force_login(self.pharm_user)
        response = self.client.get(f"/prescriptions/{self.presc_doc1.pk}/print/")
        self.assertEqual(response.status_code, 200)

        # Reception receives 403 (no view_prescription perm)
        self.client.force_login(self.reception_user)
        response = self.client.get(f"/prescriptions/{self.presc_doc1.pk}/print/")
        self.assertEqual(response.status_code, 403)

    def test_patient_document_download_privacy_and_non_disclosure(self):
        # Doctor 1 has access to Patient A, can download clean document
        self.client.force_login(self.doc1_user)
        response = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/"
        )
        self.assertEqual(response.status_code, 200)

        # Doctor 2 does not have access to Patient A, receives non-disclosing 404
        self.client.force_login(self.doc2_user)
        response = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.clean_doc.public_id}/download/"
        )
        self.assertEqual(response.status_code, 404)

        # Non-existent document or wrong patient ID returns non-disclosing 404
        self.client.force_login(self.doc1_user)
        response = self.client.get(
            f"/patients/{self.patient_b.pk}/documents/{self.clean_doc.public_id}/download/"
        )
        self.assertEqual(response.status_code, 404)

        # Rejected document is not clean, returns non-disclosing 404
        response = self.client.get(
            f"/patients/{self.patient_a.pk}/documents/{self.rejected_doc.public_id}/download/"
        )
        self.assertEqual(response.status_code, 404)

    def test_ipd_admission_and_deposit_authorization(self):
        # Reception and Administrator can view admission detail
        self.client.force_login(self.reception_user)
        response = self.client.get(f"/ipd/admissions/{self.admission.pk}/")
        self.assertEqual(response.status_code, 200)

        # Doctor can view admission detail
        self.client.force_login(self.doc1_user)
        response = self.client.get(f"/ipd/admissions/{self.admission.pk}/")
        self.assertEqual(response.status_code, 200)

        # Pharmacy cannot view admission (403)
        self.client.force_login(self.pharm_user)
        response = self.client.get(f"/ipd/admissions/{self.admission.pk}/")
        self.assertEqual(response.status_code, 403)

        # Doctor cannot create inpatient advance deposit (403)
        self.client.force_login(self.doc1_user)
        response = self.client.post(
            f"/ipd/admissions/{self.admission.pk}/deposits/create/",
            {"amount": "1000.00", "payment_method": self.payment_method.pk},
        )
        self.assertEqual(response.status_code, 403)

        # Reception can record inpatient advance deposit
        self.client.force_login(self.reception_user)
        response = self.client.post(
            f"/ipd/admissions/{self.admission.pk}/deposits/create/",
            {
                "amount": "1000.00",
                "payment_method": self.payment_method.pk,
                "transaction_reference": "DEP-REF-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.admission.deposits.count(), 1)

    def test_pharmacy_actions_restricted_to_pharmacy_role(self):
        # Doctors and Receptionists cannot create stock receipts or adjust stock
        for user in (self.doc1_user, self.reception_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get("/pharmacy/prescriptions/").status_code, 403)
                self.assertEqual(self.client.post("/pharmacy/stock-receipts/create/").status_code, 403)

        # Pharmacy can access prescription list
        self.client.force_login(self.pharm_user)
        response = self.client.get("/pharmacy/prescriptions/")
        self.assertEqual(response.status_code, 200)


class PatientDataIsolationTests(TestCase):
    """Verifies that two patients can never access each other's data across API and portals."""

    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)

        # Create Patient 1
        cls.user_p1 = User.objects.create_user("patient1", password="Password123!")
        cls.patient1 = Patient.objects.create(mrn="PAT-001", full_name="Patient One")
        PatientAccount.objects.create(user=cls.user_p1, patient=cls.patient1, is_verified=True)

        # Create Patient 2
        cls.user_p2 = User.objects.create_user("patient2", password="Password123!")
        cls.patient2 = Patient.objects.create(mrn="PAT-002", full_name="Patient Two")
        PatientAccount.objects.create(user=cls.user_p2, patient=cls.patient2, is_verified=True)

        # Doctor for consultations & documents
        cls.dept = Department.objects.create(code="MED", name="Medicine")
        cls.doc_user = User.objects.create_user("doc_p")
        cls.doc_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc_profile = StaffProfile.objects.create(
            user=cls.doc_user, employee_id="DOC-P", department=cls.dept
        )
        cls.visit_type = VisitType.objects.create(code="V1", name="Visit 1")

        # Patient 1 Appointment & Invoice
        cls.apt_p1 = Appointment.objects.create(
            patient=cls.patient1,
            doctor=cls.doc_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
        )
        cls.inv_p1 = Invoice.objects.create(
            number="INV-P1-001",
            patient=cls.patient1,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            issued_at=timezone.now(),
            created_by=cls.doc_profile,
        )

        # Patient 2 Appointment & Invoice
        cls.apt_p2 = Appointment.objects.create(
            patient=cls.patient2,
            doctor=cls.doc_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
        )
        cls.inv_p2 = Invoice.objects.create(
            number="INV-P2-001",
            patient=cls.patient2,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("200.00"),
            total=Decimal("200.00"),
            issued_at=timezone.now(),
            created_by=cls.doc_profile,
        )

        # Documents
        def _make_doc(patient, title, val_status, released_at=None, revoked_at=None):
            content = f"%PDF-1.4 test document content {title}".encode()
            doc = PatientDocument(
                patient=patient,
                uploaded_by=cls.doc_profile,
                document_type=PatientDocument.DocumentType.LAB_REPORT,
                title=title,
                content_type="application/pdf",
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                validation_status=val_status,
                patient_released_at=released_at,
                patient_access_revoked_at=revoked_at,
            )
            doc.file.save(f"{title}.pdf", ContentFile(content), save=False)
            doc.save()
            return doc

        cls.doc_p1 = _make_doc(
            cls.patient1, "P1 Report", PatientDocument.ValidationStatus.CLEAN, released_at=timezone.now()
        )
        cls.doc_p2 = _make_doc(
            cls.patient2, "P2 Report", PatientDocument.ValidationStatus.CLEAN, released_at=timezone.now()
        )

    def _auth_headers(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_patient_cannot_access_staff_views_directly(self):
        self.client.force_login(self.user_p1)
        # Directly accessing staff URLs returns 403 or redirects
        self.assertEqual(self.client.get("/patients/").status_code, 403)
        self.assertEqual(self.client.get(f"/patients/{self.patient1.pk}/").status_code, 403)
        self.assertEqual(self.client.get(f"/patients/{self.patient2.pk}/").status_code, 403)
        self.assertEqual(self.client.get(f"/invoices/{self.inv_p1.pk}/").status_code, 403)
        self.assertEqual(self.client.get("/appointments/").status_code, 403)

    def test_two_patients_cannot_cross_download_documents(self):
        # Patient 1 cannot download Patient 2's document via API
        response = self.client.get(
            f"/api/v1/me/documents/{self.doc_p2.public_id}/download/",
            **self._auth_headers(self.user_p1),
        )
        self.assertEqual(response.status_code, 404)

        # Patient 1 can download own document
        response = self.client.get(
            f"/api/v1/me/documents/{self.doc_p1.public_id}/download/",
            **self._auth_headers(self.user_p1),
        )
        self.assertEqual(response.status_code, 200)

        # Patient 2 cannot download Patient 1's document via API
        response = self.client.get(
            f"/api/v1/me/documents/{self.doc_p1.public_id}/download/",
            **self._auth_headers(self.user_p2),
        )
        self.assertEqual(response.status_code, 404)

        # Patient 2 can download own document
        response = self.client.get(
            f"/api/v1/me/documents/{self.doc_p2.public_id}/download/",
            **self._auth_headers(self.user_p2),
        )
        self.assertEqual(response.status_code, 200)

    def test_two_patients_cannot_see_other_invoices(self):
        # Patient 1 gets only their own invoices
        response = self.client.get("/api/v1/me/invoices/", **self._auth_headers(self.user_p1))
        self.assertEqual(response.status_code, 200)
        numbers = [inv["number"] for inv in response.json()]
        self.assertIn("INV-P1-001", numbers)
        self.assertNotIn("INV-P2-001", numbers)

        # Patient 2 gets only their own invoices
        response = self.client.get("/api/v1/me/invoices/", **self._auth_headers(self.user_p2))
        self.assertEqual(response.status_code, 200)
        numbers = [inv["number"] for inv in response.json()]
        self.assertIn("INV-P2-001", numbers)
        self.assertNotIn("INV-P1-001", numbers)
