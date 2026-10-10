from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.models import (
    Admission,
    AuditEvent,
    Bed,
    InpatientDeposit,
    NumberSequence,
    Patient,
    PaymentMethod,
    StaffProfile,
    Ward,
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
class IPDWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        NumberSequence.objects.create(code="ADMISSION", prefix="ADM-", next_value=300)
        NumberSequence.objects.create(code="DEPOSIT", prefix="DEP-", next_value=300)

        # Doctor
        cls.doc_user = User.objects.create_user("doc_ipd_user", password="password")
        cls.doc_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc_profile = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-IPD-01",
        )

        # Reception
        cls.reception_user = User.objects.create_user("rec_ipd_user", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC-IPD-01",
        )

        # Administrator
        cls.admin_user = User.objects.create_user("adm_ipd_user", password="password", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM-IPD-01",
        )

        # Pharmacy
        cls.pharmacy_user = User.objects.create_user("phm_ipd_user", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM-IPD-01",
        )

        # Patients
        cls.patient = Patient.objects.create(
            mrn="PAT-IPD-001",
            full_name="Ian Inpatient",
        )

        # Ward and Beds
        cls.ward = Ward.objects.create(
            name="Deluxe Private Ward",
            code="DPW",
            category=Ward.Category.PRIVATE,
            daily_rate=Decimal("2500.00"),
        )
        cls.bed_available = Bed.objects.create(
            ward=cls.ward,
            bed_number="DPW-101",
            status=Bed.Status.AVAILABLE,
        )
        cls.bed_occupied = Bed.objects.create(
            ward=cls.ward,
            bed_number="DPW-102",
            status=Bed.Status.OCCUPIED,
        )

        # Existing active admission
        cls.admission = Admission.objects.create(
            admission_number="ADM-000301",
            patient=cls.patient,
            bed=cls.bed_occupied,
            admitting_doctor=cls.doc_profile,
            admitted_by=cls.reception_profile,
            admission_reason="Post-operative observation",
            status=Admission.Status.ADMITTED,
        )

        cls.payment_method = PaymentMethod.objects.create(
            name="UPI / QR Code",
            code="UPI",
            is_active=True,
        )

    def test_anonymous_redirects_to_login(self):
        response = self.client.get("/ipd/admissions/", HTTP_HOST="staff.hms.test")
        self.assertRedirects(response, "/accounts/login/?next=/ipd/admissions/", fetch_redirect_response=False)

    def test_pharmacy_role_denied_ipd_workspace(self):
        self.client.force_login(self.pharmacy_user)
        # List
        res_list = self.client.get("/ipd/admissions/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_list.status_code, 403)

        # Detail
        res_detail = self.client.get(f"/ipd/admissions/{self.admission.pk}/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_detail.status_code, 403)

    def test_reception_and_admin_see_admissions(self):
        for user in (self.reception_user, self.admin_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get("/ipd/admissions/", HTTP_HOST="staff.hms.test")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "ADM-000301")
                self.assertContains(response, "Ian Inpatient")

    def test_doctor_cannot_access_or_discharge_another_doctors_admission(self):
        other_user = User.objects.create_user("other_ipd_doctor", password="password")
        other_user.groups.add(Group.objects.get(name="Doctor"))
        other_profile = StaffProfile.objects.create(
            user=other_user,
            employee_id="DOC-IPD-OTHER",
        )
        other_patient = Patient.objects.create(
            mrn="PAT-IPD-OTHER",
            full_name="Other Doctor Patient",
        )
        other_bed = Bed.objects.create(
            ward=self.ward,
            bed_number="DPW-OTHER",
            status=Bed.Status.OCCUPIED,
        )
        other_admission = Admission.objects.create(
            admission_number="ADM-OTHER",
            patient=other_patient,
            bed=other_bed,
            admitting_doctor=other_profile,
            admitted_by=self.reception_profile,
            admission_reason="Scoped admission",
        )

        self.client.force_login(self.doc_user)
        listing = self.client.get("/ipd/admissions/", HTTP_HOST="staff.hms.test")
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, self.admission.admission_number)
        self.assertNotContains(listing, other_admission.admission_number)
        self.assertEqual(
            self.client.get(
                f"/ipd/admissions/{other_admission.pk}/",
                HTTP_HOST="staff.hms.test",
            ).status_code,
            404,
        )
        discharge = self.client.post(
            f"/ipd/admissions/{other_admission.pk}/discharge/",
            {
                "status": Admission.Status.DISCHARGED,
                "discharge_condition": "Stable",
                "discharge_summary": "Must not be accepted.",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(discharge.status_code, 404)
        other_admission.refresh_from_db()
        self.assertEqual(other_admission.status, Admission.Status.ADMITTED)

    def test_admission_creation_locks_bed_and_snapshots_daily_rate(self):
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/ipd/admissions/create/",
            {
                "patient": self.patient.pk,
                "bed": self.bed_available.pk,
                "admitting_doctor": self.doc_profile.pk,
                "admission_reason": "Acute exacerbation",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        new_adm = Admission.objects.get(bed=self.bed_available)
        self.assertEqual(new_adm.status, Admission.Status.ADMITTED)
        # Verify daily rate snapshot
        self.assertEqual(new_adm.daily_rate_snapshot, Decimal("2500.00"))

        # Verify bed is marked occupied
        self.bed_available.refresh_from_db()
        self.assertEqual(self.bed_available.status, Bed.Status.OCCUPIED)

        # Verify retroactive ward rate change does not alter admission snapshot
        self.ward.daily_rate = Decimal("3500.00")
        self.ward.save()
        new_adm.refresh_from_db()
        self.assertEqual(new_adm.daily_rate_snapshot, Decimal("2500.00"))

    def test_occupied_bed_cannot_be_allocated(self):
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/ipd/admissions/create/",
            {
                "patient": self.patient.pk,
                "bed": self.bed_occupied.pk,
                "admitting_doctor": self.doc_profile.pk,
                "admission_reason": "Double booking test",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")

    def test_inpatient_deposit_creation_and_audit(self):
        self.client.force_login(self.reception_user)
        response = self.client.post(
            f"/ipd/admissions/{self.admission.pk}/deposits/create/",
            {
                "amount": "5000.00",
                "payment_method": self.payment_method.pk,
                "transaction_reference": "TXN12345",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        deposit = InpatientDeposit.objects.filter(admission=self.admission).first()
        self.assertIsNotNone(deposit)
        self.assertEqual(deposit.amount, Decimal("5000.00"))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="ipd.deposit_received",
                target_id=str(self.patient.pk),
            ).exists()
        )

    def test_patient_discharge_frees_bed_and_records_audit(self):
        self.client.force_login(self.doc_user)
        response = self.client.post(
            f"/ipd/admissions/{self.admission.pk}/discharge/",
            {
                "status": Admission.Status.DISCHARGED,
                "discharge_condition": "Stable / Recovered",
                "discharge_summary": "Patient showed complete recovery after 48h observation.",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        self.admission.refresh_from_db()
        self.assertEqual(self.admission.status, Admission.Status.DISCHARGED)
        self.assertIsNotNone(self.admission.discharged_at)

        # Verify bed is marked available
        self.bed_occupied.refresh_from_db()
        self.assertEqual(self.bed_occupied.status, Bed.Status.AVAILABLE)

        self.assertTrue(
            AuditEvent.objects.filter(
                action="ipd.patient_discharged",
                target_id=str(self.patient.pk),
            ).exists()
        )
