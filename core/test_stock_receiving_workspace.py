import uuid
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    AuditEvent,
    Medicine,
    MedicineBatch,
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
class StockReceivingWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from core.models import NumberSequence
        NumberSequence.objects.get_or_create(code="STOCK_RECEIPT", defaults={"prefix": "REC-", "next_value": 1000})
        configure_role_permissions()

        cls.doctor_user = User.objects.create_user("doctor_rcv", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user, employee_id="DOC-RCV-1"
        )

        cls.reception_user = User.objects.create_user("rec_rcv", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user, employee_id="REC-RCV-1"
        )

        cls.pharmacy_user = User.objects.create_user("pharm_rcv", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user, employee_id="PHM-RCV-1"
        )

        cls.admin_user = User.objects.create_user(
            "admin_rcv", password="password", is_staff=True
        )
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user, employee_id="ADM-RCV-1"
        )

        cls.ordinary_user = User.objects.create_user("ord_rcv", password="password")

        cls.supplier = Supplier.objects.create(
            code="SUP-RCV-01",
            name="Apex Healthcare Supplies",
            phone="+91 9111122222",
            email="apex@supplies.test",
            is_active=True,
        )

        cls.inactive_supplier = Supplier.objects.create(
            code="SUP-INACTIVE",
            name="Defunct Supply Co",
            is_active=False,
        )

        cls.med_cipro = Medicine.objects.create(
            code="MED-CIPRO-500",
            generic_name="Ciprofloxacin",
            strength="500mg",
            dosage_form="Tablet",
            unit="tablet",
            is_otc=False,
            is_active=True,
        )

        cls.med_inactive = Medicine.objects.create(
            code="MED-OLD-DISCONTINUED",
            generic_name="Discontinued Elixir",
            unit="bottle",
            is_active=False,
        )

        cls.existing_receipt = StockReceipt.objects.create(
            number="REC-HIST-INIT",
            supplier=cls.supplier,
            supplier_reference="INV-HIST-101",
            received_at=timezone.now(),
            received_by=cls.pharmacy_profile,
        )
        cls.existing_batch = MedicineBatch.objects.create(
            medicine=cls.med_cipro,
            receipt=cls.existing_receipt,
            batch_number="BAT-INIT-99",
            expiry_date=timezone.localdate() + timedelta(days=180),
            purchase_price=Decimal("4.00"),
            sale_price=Decimal("7.00"),
            quantity_received=Decimal("50"),
            quantity_on_hand=Decimal("50"),
        )

    def test_anonymous_access_redirects(self):
        res = self.client.get("/store/receipts/", HTTP_HOST="store.hms.test")
        self.assertRedirects(res, "/accounts/login/?next=/store/receipts/")

    def test_unauthorized_roles_forbidden(self):
        for user in [self.doctor_user, self.reception_user, self.ordinary_user]:
            self.client.force_login(user)
            res = self.client.get("/store/receipts/", HTTP_HOST="store.hms.test")
            self.assertEqual(res.status_code, 403, f"User {user.username} should get 403")

            res_post = self.client.post(
                "/pharmacy/stock-receipts/create/", {}, HTTP_HOST="store.hms.test"
            )
            self.assertEqual(res_post.status_code, 403)

    def test_authorized_roles_access(self):
        self.client.force_login(self.pharmacy_user)
        res = self.client.get("/store/receipts/", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Stock Receiving &amp; Receipts")
        self.assertContains(res, "Apex Healthcare Supplies")
        self.assertContains(res, "REC-HIST-INIT")
        self.assertContains(res, "Receive Stock Delivery")

        self.client.force_login(self.admin_user)
        res_adm = self.client.get("/store/receipts/", HTTP_HOST="store.hms.test")
        self.assertEqual(res_adm.status_code, 200)
        self.assertContains(res_adm, "REC-HIST-INIT")

    def test_atomic_stock_receiving_workflow(self):
        self.client.force_login(self.pharmacy_user)
        req_key = uuid.uuid4()
        expiry = timezone.localdate() + timedelta(days=365)

        payload = {
            "request_key": str(req_key),
            "supplier": self.supplier.pk,
            "supplier_reference": "INV-APEX-2026-001",
            "medicine": self.med_cipro.pk,
            "batch_number": "BAT-CIPRO-NEW",
            "expiry_date": str(expiry),
            "quantity_received": "100.000",
            "purchase_price": "4.50",
            "sale_price": "7.50",
            "next": "/store/receipts/",
        }

        res = self.client.post(
            "/pharmacy/stock-receipts/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res, "/store/receipts/")

        # Verify StockReceipt
        receipt = StockReceipt.objects.filter(
            supplier_reference="INV-APEX-2026-001"
        ).first()
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.supplier, self.supplier)
        self.assertEqual(receipt.received_by, self.pharmacy_profile)

        # Verify MedicineBatch
        batch = MedicineBatch.objects.get(batch_number="BAT-CIPRO-NEW")
        self.assertEqual(batch.medicine, self.med_cipro)
        self.assertEqual(batch.receipt, receipt)
        self.assertEqual(batch.quantity_received, Decimal("100.000"))
        self.assertEqual(batch.quantity_on_hand, Decimal("100.000"))
        self.assertEqual(batch.purchase_price, Decimal("4.50"))
        self.assertEqual(batch.sale_price, Decimal("7.50"))
        self.assertEqual(batch.expiry_date, expiry)

        # Verify StockMovement ledger
        movement = StockMovement.objects.filter(request_key=req_key).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.batch, batch)
        self.assertEqual(movement.kind, StockMovement.Kind.RECEIPT)
        self.assertEqual(movement.quantity_delta, Decimal("100.000"))
        self.assertEqual(movement.quantity_before, Decimal("0.000"))
        self.assertEqual(movement.quantity_after, Decimal("100.000"))
        self.assertEqual(movement.reference_type, "stock_receipt")
        self.assertEqual(movement.reference_id, str(receipt.pk))

        # Verify AuditEvent
        audit = AuditEvent.objects.filter(
            target_type="stockreceipt", target_id=str(receipt.pk), action="stock.received"
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details["batch_number"], "BAT-CIPRO-NEW")

    def test_idempotent_stock_receipt_intake(self):
        self.client.force_login(self.pharmacy_user)
        req_key = uuid.uuid4()
        expiry = timezone.localdate() + timedelta(days=200)

        payload = {
            "request_key": str(req_key),
            "supplier": self.supplier.pk,
            "supplier_reference": "INV-IDEMPOTENT",
            "medicine": self.med_cipro.pk,
            "batch_number": "BAT-IDEM-01",
            "expiry_date": str(expiry),
            "quantity_received": "20.000",
            "purchase_price": "3.00",
            "sale_price": "5.00",
            "next": "/store/receipts/",
        }

        # First POST
        res1 = self.client.post(
            "/pharmacy/stock-receipts/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res1, "/store/receipts/")
        self.assertEqual(MedicineBatch.objects.filter(batch_number="BAT-IDEM-01").count(), 1)

        # Second POST with duplicate request_key
        res2 = self.client.post(
            "/pharmacy/stock-receipts/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res2, "/store/receipts/")
        self.assertEqual(MedicineBatch.objects.filter(batch_number="BAT-IDEM-01").count(), 1)
        self.assertEqual(StockReceipt.objects.filter(supplier_reference="INV-IDEMPOTENT").count(), 1)

    def test_inactive_supplier_rejected(self):
        self.client.force_login(self.pharmacy_user)
        req_key = uuid.uuid4()
        payload = {
            "request_key": str(req_key),
            "supplier": self.inactive_supplier.pk,
            "medicine": self.med_cipro.pk,
            "batch_number": "BAT-FAIL-SUP",
            "expiry_date": "2029-01-01",
            "quantity_received": "10.000",
            "purchase_price": "2.00",
            "sale_price": "4.00",
        }
        res = self.client.post(
            "/pharmacy/stock-receipts/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "Cannot receive stock from an inactive supplier", status_code=400)

    def test_inactive_medicine_rejected(self):
        self.client.force_login(self.pharmacy_user)
        req_key = uuid.uuid4()
        payload = {
            "request_key": str(req_key),
            "supplier": self.supplier.pk,
            "medicine": self.med_inactive.pk,
            "batch_number": "BAT-FAIL-MED",
            "expiry_date": "2029-01-01",
            "quantity_received": "10.000",
            "purchase_price": "2.00",
            "sale_price": "4.00",
        }
        res = self.client.post(
            "/pharmacy/stock-receipts/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "Cannot receive stock for an inactive medicine", status_code=400)

    def test_invalid_intake_amounts_rejected(self):
        self.client.force_login(self.pharmacy_user)

        # Non-positive quantity
        payload = {
            "request_key": str(uuid.uuid4()),
            "supplier": self.supplier.pk,
            "medicine": self.med_cipro.pk,
            "batch_number": "BAT-INVALID-QTY",
            "expiry_date": "2029-01-01",
            "quantity_received": "-5.000",
            "purchase_price": "2.00",
            "sale_price": "4.00",
        }
        res = self.client.post(
            "/pharmacy/stock-receipts/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)

        # Negative price
        payload_price = {
            "request_key": str(uuid.uuid4()),
            "supplier": self.supplier.pk,
            "medicine": self.med_cipro.pk,
            "batch_number": "BAT-INVALID-PRICE",
            "expiry_date": "2029-01-01",
            "quantity_received": "5.000",
            "purchase_price": "-2.00",
            "sale_price": "4.00",
        }
        res_price = self.client.post(
            "/pharmacy/stock-receipts/create/",
            payload_price,
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res_price.status_code, 400)
