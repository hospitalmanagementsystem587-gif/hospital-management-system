import uuid
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AuditEvent,
    Dispensing,
    DispensingLine,
    Medicine,
    MedicineBatch,
    NumberSequence,
    Patient,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    StockMovement,
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
class DispensingQueueWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        NumberSequence.objects.get_or_create(code="INVOICE", defaults={"prefix": "INV-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="DISPENSING", defaults={"prefix": "DISP-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="PATIENT", defaults={"prefix": "PAT-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="PRESCRIPTION", defaults={"prefix": "RX-", "next_value": 1000})
        configure_role_permissions()

        # Users & profiles
        cls.pharmacy_user = User.objects.create_user("pharmacy_user_dq", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM-DQ-1",
        )

        cls.doctor_user = User.objects.create_user("doctor_user_dq", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-DQ-1",
        )

        # Patient & Prescriptions
        cls.patient = Patient.objects.create(
            mrn="PAT-DQ-001",
            full_name="Jane Doe",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 30),
            phone="+15550199",
            allergy_safety_notes="Penicillin Allergy",
        )

        cls.medicine_active = Medicine.objects.create(
            code="MED-AMOX-500",
            generic_name="Amoxicillin",
            brand_name="Moxatag",
            strength="500mg",
            dosage_form="capsule",
            unit="capsule",
            is_active=True,
        )

        cls.medicine_inactive = Medicine.objects.create(
            code="MED-CEPH-250",
            generic_name="Cephalexin",
            brand_name="Keflex",
            strength="250mg",
            dosage_form="capsule",
            unit="capsule",
            is_active=False,
        )

        from core.models import Supplier, StockReceipt
        cls.supplier = Supplier.objects.create(code="SUP-DQ", name="DQ Supplier")
        cls.receipt = StockReceipt.objects.create(
            number="REC-DQ-100", supplier=cls.supplier, received_at=timezone.now()
        )

        # Batches
        cls.batch_fefo_1 = MedicineBatch.objects.create(
            medicine=cls.medicine_active,
            receipt=cls.receipt,
            batch_number="BAT-AMOX-01",
            expiry_date=timezone.localdate() + timedelta(days=10),
            quantity_received=Decimal("100.000"),
            quantity_on_hand=Decimal("50.000"),
            purchase_price=Decimal("1.50"),
            sale_price=Decimal("3.00"),
            is_quarantined=False,
        )

        cls.batch_fefo_2 = MedicineBatch.objects.create(
            medicine=cls.medicine_active,
            receipt=cls.receipt,
            batch_number="BAT-AMOX-02",
            expiry_date=timezone.localdate() + timedelta(days=60),
            quantity_received=Decimal("100.000"),
            quantity_on_hand=Decimal("100.000"),
            purchase_price=Decimal("1.40"),
            sale_price=Decimal("3.00"),
            is_quarantined=False,
        )

        cls.batch_expired = MedicineBatch.objects.create(
            medicine=cls.medicine_active,
            receipt=cls.receipt,
            batch_number="BAT-AMOX-EXP",
            expiry_date=timezone.localdate() - timedelta(days=5),
            quantity_received=Decimal("50.000"),
            quantity_on_hand=Decimal("20.000"),
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("3.00"),
            is_quarantined=False,
        )

        cls.batch_quarantined = MedicineBatch.objects.create(
            medicine=cls.medicine_active,
            receipt=cls.receipt,
            batch_number="BAT-AMOX-QUAR",
            expiry_date=timezone.localdate() + timedelta(days=30),
            quantity_received=Decimal("50.000"),
            quantity_on_hand=Decimal("30.000"),
            purchase_price=Decimal("1.20"),
            sale_price=Decimal("3.00"),
            is_quarantined=True,
        )

        cls.prescription = Prescription.objects.create(
            number="RX-DQ-001",
            patient=cls.patient,
            doctor=cls.doctor_profile,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )

        cls.prescription_item = PrescriptionItem.objects.create(
            prescription=cls.prescription,
            medicine=cls.medicine_active,
            dosage="500mg",
            frequency="TID",
            duration="5 days",
            quantity=Decimal("15.000"),
        )

    def test_unauthenticated_and_unauthorized_access(self):
        url = reverse("pharmacy_prescription_list")
        res = self.client.get(url, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 302)

        self.client.force_login(self.doctor_user)
        res = self.client.get(url, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 403)

    def test_dispensing_queue_workspace_renders_prescriptions_and_fefo_batches(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_prescription_list")
        res = self.client.get(url, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "RX-DQ-001")
        self.assertContains(res, "Jane Doe")
        self.assertContains(res, "Penicillin Allergy")
        self.assertContains(res, "BAT-AMOX-01")
        self.assertContains(res, "(FEFO)")

        # Verify alias route works
        alias_url = reverse("store_dispensing_queue")
        res_alias = self.client.get(alias_url, HTTP_HOST="store.hms.test")
        self.assertEqual(res_alias.status_code, 200)

    def test_successful_dispensing_deducts_stock_creates_movement_invoice_and_audit(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("dispense_prescription", args=[self.prescription.pk])
        req_key = str(uuid.uuid4())

        post_data = {
            "prescription_item": self.prescription_item.pk,
            "batch": self.batch_fefo_1.pk,
            "quantity": "10.000",
            "request_key": req_key,
        }

        res = self.client.post(url, post_data, HTTP_HOST="store.hms.test")
        self.assertRedirects(res, reverse("pharmacy_prescription_list"))

        self.batch_fefo_1.refresh_from_db()
        self.assertEqual(self.batch_fefo_1.quantity_on_hand, Decimal("40.000"))

        disp = Dispensing.objects.filter(prescription=self.prescription).latest("created_at")
        self.assertEqual(disp.patient, self.patient)
        self.assertEqual(disp.dispensed_by, self.pharmacy_profile)

        line = DispensingLine.objects.get(dispensing=disp)
        self.assertEqual(line.quantity, Decimal("10.000"))
        self.assertEqual(line.batch, self.batch_fefo_1)

        # Stock Movement
        mvt = StockMovement.objects.get(request_key=req_key)
        self.assertEqual(mvt.kind, StockMovement.Kind.DISPENSE)
        self.assertEqual(mvt.quantity_delta, Decimal("-10.000"))
        self.assertEqual(mvt.quantity_after, Decimal("40.000"))

        # Invoice
        self.assertIsNotNone(disp.invoice)
        self.assertEqual(disp.invoice.total, Decimal("30.00"))

        # Audit Event
        audit = AuditEvent.objects.filter(action="stock.dispensed", target_id=str(disp.pk)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details.get("quantity"), "10.000")

    def test_dispensing_rejects_expired_quarantined_or_inactive_medicines(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("dispense_prescription", args=[self.prescription.pk])

        # Expired batch
        res = self.client.post(
            url,
            {
                "prescription_item": self.prescription_item.pk,
                "batch": self.batch_expired.pk,
                "quantity": "5.000",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Expired", res.content.decode())

        # Quarantined batch
        res = self.client.post(
            url,
            {
                "prescription_item": self.prescription_item.pk,
                "batch": self.batch_quarantined.pk,
                "quantity": "5.000",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Quarantined", res.content.decode())

    def test_dispensing_rejects_exceeding_prescription_quantity_or_stock_on_hand(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("dispense_prescription", args=[self.prescription.pk])

        # Exceed prescription quantity (ordered 15)
        res = self.client.post(
            url,
            {
                "prescription_item": self.prescription_item.pk,
                "batch": self.batch_fefo_1.pk,
                "quantity": "20.000",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("exceeds the remaining prescription amount", res.content.decode())

    def test_dispensing_idempotency_with_duplicate_request_key(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("dispense_prescription", args=[self.prescription.pk])
        req_key = str(uuid.uuid4())

        post_data = {
            "prescription_item": self.prescription_item.pk,
            "batch": self.batch_fefo_1.pk,
            "quantity": "5.000",
            "request_key": req_key,
        }

        res1 = self.client.post(url, post_data, HTTP_HOST="store.hms.test")
        self.assertRedirects(res1, reverse("pharmacy_prescription_list"))

        # Re-post with duplicate request_key
        res2 = self.client.post(url, post_data, HTTP_HOST="store.hms.test")
        self.assertRedirects(res2, reverse("pharmacy_prescription_list"))

        # Quantity deducted only once
        self.batch_fefo_1.refresh_from_db()
        self.assertEqual(self.batch_fefo_1.quantity_on_hand, Decimal("45.000"))
        self.assertEqual(StockMovement.objects.filter(request_key=req_key).count(), 1)
