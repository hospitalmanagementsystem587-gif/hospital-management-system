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
    Invoice,
    Medicine,
    MedicineBatch,
    NumberSequence,
    Payment,
    PaymentMethod,
    PharmacySale,
    PharmacySaleLine,
    StaffProfile,
    StockMovement,
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
class PharmacySalesWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        NumberSequence.objects.get_or_create(code="INVOICE", defaults={"prefix": "INV-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="PHARMACY_SALE", defaults={"prefix": "SALE-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="RECEIPT", defaults={"prefix": "PAY-", "next_value": 1000})
        configure_role_permissions()

        cls.pharmacy_user = User.objects.create_user("pharmacy_user_pos", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM-POS-1",
        )

        cls.doctor_user = User.objects.create_user("doctor_user_pos", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-POS-1",
        )
        cls.payment_method = PaymentMethod.objects.create(
            name="UPI", code="UPI", is_active=True
        )

        cls.supplier = Supplier.objects.create(code="SUP-POS", name="POS Supplier Ltd")
        cls.receipt = StockReceipt.objects.create(
            number="REC-POS-100", supplier=cls.supplier, received_at=timezone.now()
        )

        cls.otc_med = Medicine.objects.create(
            code="MED-PCM-OTC",
            generic_name="Paracetamol",
            brand_name="Dolo",
            strength="650mg",
            dosage_form="tablet",
            unit="tablet",
            is_otc=True,
            is_active=True,
        )

        cls.rx_only_med = Medicine.objects.create(
            code="MED-AMOX-RX",
            generic_name="Amoxicillin",
            brand_name="Moxatag",
            strength="500mg",
            dosage_form="capsule",
            unit="capsule",
            is_otc=False,
            is_active=True,
        )

        cls.inactive_otc_med = Medicine.objects.create(
            code="MED-IBU-INACT",
            generic_name="Ibuprofen",
            brand_name="Brufen",
            strength="400mg",
            dosage_form="tablet",
            unit="tablet",
            is_otc=True,
            is_active=False,
        )

        today = timezone.localdate()

        cls.batch_valid = MedicineBatch.objects.create(
            medicine=cls.otc_med,
            receipt=cls.receipt,
            batch_number="BAT-PCM-01",
            expiry_date=today + timedelta(days=90),
            quantity_received=Decimal("100.000"),
            quantity_on_hand=Decimal("50.000"),
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.50"),
            is_quarantined=False,
        )

        cls.batch_expired = MedicineBatch.objects.create(
            medicine=cls.otc_med,
            receipt=cls.receipt,
            batch_number="BAT-PCM-EXP",
            expiry_date=today - timedelta(days=2),
            quantity_received=Decimal("50.000"),
            quantity_on_hand=Decimal("20.000"),
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.50"),
            is_quarantined=False,
        )

        cls.batch_quarantined = MedicineBatch.objects.create(
            medicine=cls.otc_med,
            receipt=cls.receipt,
            batch_number="BAT-PCM-QUAR",
            expiry_date=today + timedelta(days=30),
            quantity_received=Decimal("50.000"),
            quantity_on_hand=Decimal("20.000"),
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.50"),
            is_quarantined=True,
        )

        cls.batch_rx = MedicineBatch.objects.create(
            medicine=cls.rx_only_med,
            receipt=cls.receipt,
            batch_number="BAT-AMOX-01",
            expiry_date=today + timedelta(days=30),
            quantity_received=Decimal("50.000"),
            quantity_on_hand=Decimal("20.000"),
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("5.00"),
            is_quarantined=False,
        )

        cls.batch_inactive = MedicineBatch.objects.create(
            medicine=cls.inactive_otc_med,
            receipt=cls.receipt,
            batch_number="BAT-IBU-01",
            expiry_date=today + timedelta(days=30),
            quantity_received=Decimal("50.000"),
            quantity_on_hand=Decimal("20.000"),
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("3.00"),
            is_quarantined=False,
        )

    def test_unauthorized_access_prevented(self):
        url = reverse("pharmacy_sale_create")
        res = self.client.post(url, {}, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 302)

        self.client.force_login(self.doctor_user)
        res = self.client.post(url, {}, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 403)

    def test_successful_otc_sale_creates_invoice_and_stock_movement(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_sale_create")
        req_key = str(uuid.uuid4())

        post_data = {
            "batch": self.batch_valid.pk,
            "quantity": "4.000",
            "request_key": req_key,
            "payment_method": self.payment_method.pk,
            "payment_reference": "UPI-REF-1001",
        }

        res = self.client.post(url, post_data, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 302)

        sale = PharmacySale.objects.latest("created_at")
        self.assertRedirects(res, reverse("pharmacy_sale_detail", args=[sale.pk]))

        self.batch_valid.refresh_from_db()
        self.assertEqual(self.batch_valid.quantity_on_hand, Decimal("46.000"))

        self.assertEqual(sale.sold_by, self.pharmacy_profile)
        line = PharmacySaleLine.objects.get(sale=sale)
        self.assertEqual(line.batch, self.batch_valid)
        self.assertEqual(line.quantity, Decimal("4.000"))
        self.assertEqual(line.unit_price, Decimal("2.50"))
        self.assertEqual(line.line_total, Decimal("10.00"))

        invoice = sale.invoice
        self.assertIsNone(invoice.patient)
        self.assertEqual(invoice.total, Decimal("10.00"))
        payment = Payment.objects.get(invoice=invoice)
        self.assertEqual(payment.amount, Decimal("10.00"))
        self.assertEqual(payment.method, self.payment_method)
        self.assertEqual(payment.reference, "UPI-REF-1001")

        mvt = StockMovement.objects.get(request_key=req_key)
        self.assertEqual(mvt.kind, StockMovement.Kind.SALE)
        self.assertEqual(mvt.quantity_delta, Decimal("-4.000"))
        self.assertEqual(mvt.quantity_after, Decimal("46.000"))

        audit = AuditEvent.objects.get(action="pharmacy.sale_created", target_id=str(sale.pk))
        self.assertEqual(audit.details.get("invoice_id"), invoice.pk)

    def test_sale_detail_view_permissions_and_contents(self):
        self.client.force_login(self.pharmacy_user)
        sale = PharmacySale.objects.create(
            number="SALE-TEST-001",
            invoice=Invoice.objects.create(
                number="INV-TEST-001",
                patient=None,
                status=Invoice.Status.ISSUED,
                subtotal=Decimal("5.00"),
                tax_total=Decimal("0.00"),
                total=Decimal("5.00"),
                issued_at=timezone.now(),
                created_by=self.pharmacy_profile,
            ),
            status=PharmacySale.Status.ISSUED,
            sold_at=timezone.now(),
            sold_by=self.pharmacy_profile,
        )
        PharmacySaleLine.objects.create(
            sale=sale,
            batch=self.batch_valid,
            quantity=Decimal("2.000"),
            unit_price=Decimal("2.50"),
            line_total=Decimal("5.00"),
        )

        # Anonymous / doctor rejected
        self.client.logout()
        res = self.client.get(reverse("pharmacy_sale_detail", args=[sale.pk]), HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 302)

        self.client.force_login(self.doctor_user)
        res = self.client.get(reverse("pharmacy_sale_detail", args=[sale.pk]), HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 403)

        # Pharmacist allowed
        self.client.force_login(self.pharmacy_user)
        res = self.client.get(reverse("pharmacy_sale_detail", args=[sale.pk]), HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SALE-TEST-001")
        self.assertContains(res, "BAT-PCM-01")
        self.assertContains(res, "INV-TEST-001")

    def test_sale_rejects_non_otc_expired_or_quarantined_batches(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_sale_create")

        # Non-OTC
        res = self.client.post(
            url,
            {"batch": self.batch_rx.pk, "quantity": "1.000", "request_key": str(uuid.uuid4())},
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("not approved for OTC", res.content.decode())

        # Expired
        res = self.client.post(
            url,
            {"batch": self.batch_expired.pk, "quantity": "1.000", "request_key": str(uuid.uuid4())},
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Expired stock", res.content.decode())

        # Quarantined
        res = self.client.post(
            url,
            {"batch": self.batch_quarantined.pk, "quantity": "1.000", "request_key": str(uuid.uuid4())},
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Quarantined stock", res.content.decode())

        # Inactive medicine
        res = self.client.post(
            url,
            {"batch": self.batch_inactive.pk, "quantity": "1.000", "request_key": str(uuid.uuid4())},
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("not approved for OTC", res.content.decode())

    def test_sale_rejects_exceeding_stock_and_negative_quantities(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_sale_create")

        # Exceeds available stock
        res = self.client.post(
            url,
            {"batch": self.batch_valid.pk, "quantity": "999.000", "request_key": str(uuid.uuid4())},
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Insufficient stock", res.content.decode())

        # Negative / zero quantity
        res = self.client.post(
            url,
            {"batch": self.batch_valid.pk, "quantity": "-5.000", "request_key": str(uuid.uuid4())},
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)

    def test_sale_idempotency_with_duplicate_request_key(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_sale_create")
        req_key = str(uuid.uuid4())

        payload = {
            "batch": self.batch_valid.pk,
            "quantity": "2.000",
            "request_key": req_key,
            "payment_method": self.payment_method.pk,
            "payment_reference": "IDEMPOTENT-PAYMENT",
        }

        res1 = self.client.post(url, payload, HTTP_HOST="store.hms.test")
        self.assertEqual(res1.status_code, 302)

        sale = PharmacySale.objects.latest("created_at")
        self.assertRedirects(res1, reverse("pharmacy_sale_detail", args=[sale.pk]))

        # Re-submit duplicate
        res2 = self.client.post(url, payload, HTTP_HOST="store.hms.test")
        self.assertRedirects(res2, reverse("pharmacy_sale_detail", args=[sale.pk]))

        self.batch_valid.refresh_from_db()
        self.assertEqual(self.batch_valid.quantity_on_hand, Decimal("48.000"))
        self.assertEqual(PharmacySale.objects.filter(lines__batch=self.batch_valid).count(), 1)
