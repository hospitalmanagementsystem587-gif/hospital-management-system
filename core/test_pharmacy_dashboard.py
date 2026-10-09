from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Consultation,
    Invoice,
    Medicine,
    MedicineBatch,
    Patient,
    PharmacySale,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    StockReceipt,
    Supplier,
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
class PharmacyDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.doctor_user = User.objects.create_user("doctor_pharm", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user, employee_id="DOC-PHARM-1"
        )

        cls.reception_user = User.objects.create_user("rec_pharm", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user, employee_id="REC-PHARM-1"
        )

        cls.pharmacy_user = User.objects.create_user("pharm_user", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user, employee_id="PHM-PHARM-1"
        )

        cls.admin_user = User.objects.create_user(
            "admin_pharm", password="password", is_staff=True
        )
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user, employee_id="ADM-PHARM-1"
        )

        cls.ordinary_user = User.objects.create_user("ord_user", password="password")

    def test_anonymous_access_redirects_to_login(self):
        # On store portal host
        response = self.client.get("/", HTTP_HOST="store.hms.test")
        self.assertRedirects(response, "/accounts/login/?next=/", fetch_redirect_response=False)

        # On direct pharmacy dashboard endpoint
        response_direct = self.client.get("/pharmacy/", HTTP_HOST="staff.hms.test")
        self.assertRedirects(
            response_direct, "/accounts/login/?next=/pharmacy/", fetch_redirect_response=False
        )

    def test_unauthorized_roles_receive_403(self):
        for user in (self.doctor_user, self.reception_user, self.ordinary_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get("/", HTTP_HOST="store.hms.test")
                self.assertEqual(response.status_code, 403)

                response_direct = self.client.get("/pharmacy/", HTTP_HOST="staff.hms.test")
                self.assertEqual(response_direct.status_code, 403)

    def test_pharmacy_and_administrator_access(self):
        for user in (self.pharmacy_user, self.admin_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get("/", HTTP_HOST="store.hms.test")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Pharmacy Dashboard")
                self.assertContains(response, "Store portal")

    def test_bounded_aggregate_metrics_accuracy(self):
        today = timezone.localdate()
        patient = Patient.objects.create(
            mrn="PAT-PHARM-01",
            full_name="Confidential Pharmacy Patient",
            allergy_safety_notes="Severe Penicillin allergy",
        )
        consult = Consultation.objects.create(
            doctor=self.doctor_profile,
            patient=patient,
            diagnosis="Acute Bronchitis",
            clinical_notes="Confidential clinical notes about patient lungs",
        )
        rx_issued = Prescription.objects.create(
            consultation=consult,
            patient=patient,
            doctor=self.doctor_profile,
            number="RX-PHARM-101",
            status=Prescription.Status.ISSUED,
        )
        rx_dispensed = Prescription.objects.create(
            consultation=consult,
            patient=patient,
            doctor=self.doctor_profile,
            number="RX-PHARM-102",
            status=Prescription.Status.CANCELLED,
        )

        med_active1 = Medicine.objects.create(
            code="MED-PHARM-01",
            generic_name="Amoxicillin",
            unit="capsule",
            is_active=True,
        )
        med_active2 = Medicine.objects.create(
            code="MED-PHARM-02",
            generic_name="Paracetamol",
            unit="tablet",
            is_active=True,
        )
        med_inactive = Medicine.objects.create(
            code="MED-PHARM-03",
            generic_name="Banned Compound",
            unit="tablet",
            is_active=False,
        )

        supplier = Supplier.objects.create(code="SUPP-01", name="Pharma Corp")
        receipt = StockReceipt.objects.create(
            number="REC-001",
            supplier=supplier,
            received_at=timezone.now(),
        )

        # 1 Low stock batch (qty 5 < 10, not quarantined)
        MedicineBatch.objects.create(
            medicine=med_active1,
            receipt=receipt,
            batch_number="BATCH-LOW",
            expiry_date=today + timedelta(days=60),
            purchase_price=Decimal("10.00"),
            sale_price=Decimal("15.00"),
            quantity_received=Decimal("10.000"),
            quantity_on_hand=Decimal("5"),
            is_quarantined=False,
        )
        # 1 Adequate batch (qty 50 >= 10)
        MedicineBatch.objects.create(
            medicine=med_active2,
            receipt=receipt,
            batch_number="BATCH-OK",
            expiry_date=today + timedelta(days=120),
            purchase_price=Decimal("5.00"),
            sale_price=Decimal("8.00"),
            quantity_received=Decimal("100.000"),
            quantity_on_hand=Decimal("50"),
            is_quarantined=False,
        )
        # 1 Expired batch
        MedicineBatch.objects.create(
            medicine=med_active1,
            receipt=receipt,
            batch_number="BATCH-EXP",
            expiry_date=today - timedelta(days=5),
            purchase_price=Decimal("10.00"),
            sale_price=Decimal("15.00"),
            quantity_received=Decimal("20.000"),
            quantity_on_hand=Decimal("20"),
            is_quarantined=False,
        )

        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/", HTTP_HOST="store.hms.test")
        self.assertEqual(response.status_code, 200)

        # Context metrics
        self.assertEqual(response.context["issued_prescriptions_count"], 1)
        self.assertEqual(response.context["low_stock_batches_count"], 1)
        self.assertEqual(response.context["expired_batches_count"], 1)
        self.assertEqual(response.context["active_medicines_count"], 2)

    def test_dashboard_includes_todays_sales_summary(self):
        invoice = Invoice.objects.create(
            number="INV-PHARM-DASH",
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("125.50"),
            tax_total=Decimal("0.00"),
            total=Decimal("125.50"),
            issued_at=timezone.now(),
            created_by=self.pharmacy_profile,
        )
        PharmacySale.objects.create(
            number="SALE-PHARM-DASH",
            invoice=invoice,
            status=PharmacySale.Status.ISSUED,
            sold_at=timezone.now(),
            sold_by=self.pharmacy_profile,
        )

        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/", HTTP_HOST="store.hms.test")
        self.assertEqual(response.context["today_sales_count"], 1)
        self.assertEqual(response.context["today_sales_total"], Decimal("125.50"))
        self.assertContains(response, "Today's Sales")
        self.assertContains(response, "₹125.50")

    def test_patient_pii_minimization_on_dashboard(self):
        patient = Patient.objects.create(
            mrn="PAT-PII-99",
            full_name="Secret VIP Patient",
            allergy_safety_notes="Severe Latex & Shellfish Allergy",
        )
        consult = Consultation.objects.create(
            doctor=self.doctor_profile,
            patient=patient,
            diagnosis="Highly Sensitive Psychiatric Evaluation",
            clinical_notes="Confidential psychotherapy evaluation notes",
        )
        Prescription.objects.create(
            consultation=consult,
            patient=patient,
            doctor=self.doctor_profile,
            number="RX-PII-99",
            status=Prescription.Status.ISSUED,
        )

        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/", HTTP_HOST="store.hms.test")
        self.assertEqual(response.status_code, 200)

        # Ensure no sensitive patient clinical notes or diagnoses leak on the dashboard
        self.assertNotContains(response, "Secret VIP Patient")
        self.assertNotContains(response, "Highly Sensitive Psychiatric Evaluation")
        self.assertNotContains(response, "Confidential psychotherapy evaluation notes")
        self.assertNotContains(response, "Severe Latex & Shellfish Allergy")

    def test_safe_empty_state_rendering(self):
        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/", HTTP_HOST="store.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["issued_prescriptions_count"], 0)
        self.assertEqual(response.context["low_stock_batches_count"], 0)
        self.assertEqual(response.context["expired_batches_count"], 0)
        self.assertEqual(response.context["active_medicines_count"], 0)
        self.assertEqual(response.context["today_sales_count"], 0)
        self.assertEqual(response.context["today_sales_total"], Decimal("0.00"))
        self.assertContains(response, "0")
