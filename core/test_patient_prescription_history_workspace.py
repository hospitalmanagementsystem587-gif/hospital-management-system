from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Consultation,
    Department,
    Medicine,
    Patient,
    PatientAccount,
    Prescription,
    PrescriptionItem,
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
class PatientPrescriptionHistoryWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        configure_role_permissions()

        cls.dept = Department.objects.create(
            name="Internal Medicine",
            code="MED",
            is_active=True,
        )

        cls.doc_user = User.objects.create_user(
            username="dr_shukla",
            password="DocPassword123!",
            first_name="Anand",
            last_name="Shukla",
        )
        cls.doc_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-SHUKLA",
            department=cls.dept,
            consultation_fee=500,
        )

        # Medicines
        cls.med_amox = Medicine.objects.create(
            code="MED-AMOX",
            generic_name="Amoxicillin",
            brand_name="Mox 500",
            strength="500mg",
            unit="capsule",
            is_active=True,
        )
        cls.med_pcm = Medicine.objects.create(
            code="MED-PCM",
            generic_name="Paracetamol",
            brand_name="Calpol 650",
            strength="650mg",
            unit="tablet",
            is_active=True,
        )

        # Patient 1 (Alice)
        cls.alice_user = User.objects.create_user(
            username="patient_alice",
            email="alice@test.hms",
            password="AlicePassword123!",
            first_name="Alice",
            last_name="Gupta",
        )
        cls.alice_patient = Patient.objects.create(
            mrn="MRN-ALICE-01",
            full_name="Alice Gupta",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 28),
            phone="9876543210",
            email="alice@test.hms",
        )
        cls.alice_account = PatientAccount.objects.create(
            user=cls.alice_user,
            patient=cls.alice_patient,
            is_verified=True,
        )

        # Patient 2 (Bob - other patient)
        cls.bob_user = User.objects.create_user(
            username="patient_bob",
            email="bob@test.hms",
            password="BobPassword123!",
            first_name="Bob",
            last_name="Verma",
        )
        cls.bob_patient = Patient.objects.create(
            mrn="MRN-BOB-02",
            full_name="Bob Verma",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 35),
            phone="9876543211",
            email="bob@test.hms",
        )
        cls.bob_account = PatientAccount.objects.create(
            user=cls.bob_user,
            patient=cls.bob_patient,
            is_verified=True,
        )

        # Prescriptions for Alice
        cls.alice_consultation = Consultation.objects.create(
            patient=cls.alice_patient,
            doctor=cls.doctor,
            clinical_notes="Patient complaints of fever and throat infection",
            diagnosis="Acute Pharyngitis",
        )

        # 1. Issued prescription for Alice
        cls.rx_alice_issued = Prescription.objects.create(
            number="RX-ALICE-001",
            patient=cls.alice_patient,
            doctor=cls.doctor,
            consultation=cls.alice_consultation,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=2),
        )
        PrescriptionItem.objects.create(
            prescription=cls.rx_alice_issued,
            medicine=cls.med_amox,
            dosage="500mg",
            frequency="TID",
            duration="5 days",
            quantity=15,
            instructions="Take after food",
        )
        PrescriptionItem.objects.create(
            prescription=cls.rx_alice_issued,
            medicine=cls.med_pcm,
            dosage="650mg",
            frequency="SOS",
            duration="3 days",
            quantity=6,
            instructions="For fever above 100 F",
        )

        # 2. Draft prescription for Alice (must not appear)
        cls.rx_alice_draft = Prescription.objects.create(
            number="RX-ALICE-DRAFT",
            patient=cls.alice_patient,
            doctor=cls.doctor,
            status=Prescription.Status.DRAFT,
        )

        # 3. Cancelled prescription for Alice (must not appear)
        cls.rx_alice_cancelled = Prescription.objects.create(
            number="RX-ALICE-CANCELLED",
            patient=cls.alice_patient,
            doctor=cls.doctor,
            status=Prescription.Status.CANCELLED,
            issued_at=timezone.now() - timedelta(days=10),
        )

        # 4. Unissued prescription for Alice (status=issued, but issued_at is None)
        cls.rx_alice_unissued = Prescription.objects.create(
            number="RX-ALICE-UNISSUED",
            patient=cls.alice_patient,
            doctor=cls.doctor,
            status=Prescription.Status.ISSUED,
            issued_at=None,
        )

        # Prescriptions for Bob
        cls.rx_bob = Prescription.objects.create(
            number="RX-BOB-001",
            patient=cls.bob_patient,
            doctor=cls.doctor,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=1),
        )
        PrescriptionItem.objects.create(
            prescription=cls.rx_bob,
            medicine=cls.med_pcm,
            dosage="650mg",
            frequency="BD",
            duration="2 days",
            quantity=4,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_anonymous_access_redirects_to_login(self):
        resp = self.client.get("/prescriptions/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

        resp_detail = self.client.get(f"/prescriptions/{self.rx_alice_issued.pk}/")
        self.assertEqual(resp_detail.status_code, 302)

    def test_unverified_patient_cannot_view_prescriptions(self):
        self.alice_account.is_verified = False
        self.alice_account.save(update_fields=["is_verified"])
        self.client.force_login(self.alice_user)

        resp = self.client.get("/prescriptions/")
        self.assertEqual(resp.status_code, 403)

        resp_detail = self.client.get(f"/prescriptions/{self.rx_alice_issued.pk}/")
        self.assertEqual(resp_detail.status_code, 403)

    def test_archived_patient_cannot_view_prescriptions(self):
        self.alice_patient.archived_at = timezone.now()
        self.alice_patient.save(update_fields=["archived_at"])
        self.client.force_login(self.alice_user)

        resp = self.client.get("/prescriptions/")
        self.assertEqual(resp.status_code, 403)

    def test_prescription_history_lists_only_issued_prescriptions(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get("/prescriptions/")
        self.assertEqual(resp.status_code, 200)

        # Alice's issued prescription is shown
        self.assertContains(resp, "RX-ALICE-001")
        self.assertContains(resp, "Amoxicillin")
        self.assertContains(resp, "Calpol 650")
        self.assertContains(resp, "Dr. Anand Shukla")

        # Non-issued / draft / cancelled must NOT appear
        self.assertNotContains(resp, "RX-ALICE-DRAFT")
        self.assertNotContains(resp, "RX-ALICE-CANCELLED")
        self.assertNotContains(resp, "RX-ALICE-UNISSUED")

        # Bob's prescription must NOT appear
        self.assertNotContains(resp, "RX-BOB-001")

        # Internal doctor consultation notes must NOT leak
        self.assertNotContains(resp, "Patient complaints of fever")
        self.assertNotContains(resp, "Acute Pharyngitis")

    def test_prescription_detail_view_and_items(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get(f"/prescriptions/{self.rx_alice_issued.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "RX-ALICE-001")
        self.assertContains(resp, "Amoxicillin")
        self.assertContains(resp, "Take after food")
        self.assertContains(resp, "For fever above 100 F")
        self.assertContains(resp, "15 capsule")

    def test_cannot_view_draft_or_cancelled_prescription_detail(self):
        self.client.force_login(self.alice_user)
        for rx in (self.rx_alice_draft, self.rx_alice_cancelled, self.rx_alice_unissued):
            with self.subTest(rx_number=rx.number):
                resp = self.client.get(f"/prescriptions/{rx.pk}/")
                self.assertEqual(resp.status_code, 404)

    def test_cross_patient_prescription_detail_returns_404(self):
        self.client.force_login(self.alice_user)
        # Attempt to access Bob's prescription by ID
        resp = self.client.get(f"/prescriptions/{self.rx_bob.pk}/")
        self.assertEqual(resp.status_code, 404)

    def test_cross_patient_prescription_print_returns_404(self):
        self.client.force_login(self.alice_user)
        # Attempt to print Bob's prescription
        resp = self.client.get(f"/prescriptions/{self.rx_bob.pk}/print/")
        self.assertEqual(resp.status_code, 404)

    def test_cannot_print_draft_prescription(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get(f"/prescriptions/{self.rx_alice_draft.pk}/print/")
        self.assertEqual(resp.status_code, 404)

    def test_prescription_search_filter(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get("/prescriptions/?q=Amoxicillin")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "RX-ALICE-001")

        resp_none = self.client.get("/prescriptions/?q=NonExistentMedicine")
        self.assertEqual(resp_none.status_code, 200)
        self.assertContains(resp_none, "No prescriptions recorded")
