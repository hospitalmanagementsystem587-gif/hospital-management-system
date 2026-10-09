import uuid
from datetime import timedelta
from decimal import Decimal

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
class InventoryBatchWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.doctor_user = User.objects.create_user("doctor_batch", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user, employee_id="DOC-BATCH-1"
        )

        cls.reception_user = User.objects.create_user("rec_batch", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user, employee_id="REC-BATCH-1"
        )

        cls.pharmacy_user = User.objects.create_user("pharm_batch", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user, employee_id="PHM-BATCH-1"
        )

        cls.admin_user = User.objects.create_user(
            "admin_batch", password="password", is_staff=True
        )
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user, employee_id="ADM-BATCH-1"
        )

        cls.ordinary_user = User.objects.create_user("ord_batch", password="password")

        cls.supplier = Supplier.objects.create(code="SUP-BATCH", name="Batch Pharma Ltd")
        cls.receipt = StockReceipt.objects.create(
            number="REC-BATCH-100", supplier=cls.supplier, received_at=timezone.now()
        )

        cls.med_amox = Medicine.objects.create(
            code="MED-AMOX-500",
            generic_name="Amoxicillin",
            brand_name="Amoxil",
            strength="500mg",
            dosage_form="Capsule",
            unit="capsule",
            is_otc=False,
            is_active=True,
        )

        cls.med_pcm = Medicine.objects.create(
            code="MED-PCM-650",
            generic_name="Paracetamol",
            brand_name="Dolo",
            strength="650mg",
            dosage_form="Tablet",
            unit="tablet",
            is_otc=True,
            is_active=True,
        )

        today = timezone.localdate()

        # Batch 1: FEFO priority 1 (expires in 10 days)
        cls.batch_early = MedicineBatch.objects.create(
            medicine=cls.med_amox,
            receipt=cls.receipt,
            batch_number="BAT-AMOX-EARLY",
            expiry_date=today + timedelta(days=10),
            purchase_price=Decimal("5.00"),
            sale_price=Decimal("8.00"),
            quantity_received=Decimal("100"),
            quantity_on_hand=Decimal("50"),
            is_quarantined=False,
        )

        # Batch 2: FEFO priority 2 (expires in 30 days)
        cls.batch_later = MedicineBatch.objects.create(
            medicine=cls.med_amox,
            receipt=cls.receipt,
            batch_number="BAT-AMOX-LATER",
            expiry_date=today + timedelta(days=30),
            purchase_price=Decimal("5.00"),
            sale_price=Decimal("8.00"),
            quantity_received=Decimal("100"),
            quantity_on_hand=Decimal("100"),
            is_quarantined=False,
        )

        # Batch 3: Expired batch
        cls.batch_expired = MedicineBatch.objects.create(
            medicine=cls.med_pcm,
            receipt=cls.receipt,
            batch_number="BAT-PCM-EXP",
            expiry_date=today - timedelta(days=5),
            purchase_price=Decimal("2.00"),
            sale_price=Decimal("3.50"),
            quantity_received=Decimal("200"),
            quantity_on_hand=Decimal("20"),
            is_quarantined=False,
        )

        # Batch 4: Quarantined batch
        cls.batch_quarantined = MedicineBatch.objects.create(
            medicine=cls.med_pcm,
            receipt=cls.receipt,
            batch_number="BAT-PCM-QRN",
            expiry_date=today + timedelta(days=60),
            purchase_price=Decimal("2.00"),
            sale_price=Decimal("3.50"),
            quantity_received=Decimal("50"),
            quantity_on_hand=Decimal("50"),
            is_quarantined=True,
        )

        # Batch 5: Low stock batch
        cls.batch_low_stock = MedicineBatch.objects.create(
            medicine=cls.med_pcm,
            receipt=cls.receipt,
            batch_number="BAT-PCM-LOW",
            expiry_date=today + timedelta(days=90),
            purchase_price=Decimal("2.00"),
            sale_price=Decimal("3.50"),
            quantity_received=Decimal("100"),
            quantity_on_hand=Decimal("4"),
            is_quarantined=False,
        )

        # Create initial movement for batch_early
        StockMovement.objects.create(
            batch=cls.batch_early,
            kind=StockMovement.Kind.RECEIPT,
            quantity_delta=Decimal("100"),
            quantity_before=Decimal("0"),
            quantity_after=Decimal("100"),
            reference_type="stock_receipt",
            reference_id=str(cls.receipt.pk),
            actor=cls.pharmacy_profile,
        )

    def test_anonymous_access_redirects(self):
        res = self.client.get("/store/batches/", HTTP_HOST="store.hms.test")
        self.assertRedirects(res, "/accounts/login/?next=/store/batches/")

        res_detail = self.client.get(
            f"/store/batches/{self.batch_early.pk}/", HTTP_HOST="store.hms.test"
        )
        self.assertRedirects(
            res_detail, f"/accounts/login/?next=/store/batches/{self.batch_early.pk}/"
        )

    def test_unauthorized_roles_forbidden(self):
        for user in [self.doctor_user, self.reception_user, self.ordinary_user]:
            self.client.force_login(user)
            res = self.client.get("/store/batches/", HTTP_HOST="store.hms.test")
            self.assertEqual(res.status_code, 403, f"User {user.username} should get 403")

            res_detail = self.client.get(
                f"/store/batches/{self.batch_early.pk}/", HTTP_HOST="store.hms.test"
            )
            self.assertEqual(
                res_detail.status_code, 403, f"User {user.username} detail should get 403"
            )

    def test_pharmacy_role_access(self):
        self.client.force_login(self.pharmacy_user)
        res = self.client.get("/store/batches/", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Inventory &amp; Batches")
        self.assertContains(res, "BAT-AMOX-EARLY")

        res_detail = self.client.get(
            f"/store/batches/{self.batch_early.pk}/", HTTP_HOST="store.hms.test"
        )
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "BAT-AMOX-EARLY")
        self.assertContains(res_detail, "Stock Movement Ledger")

    def test_admin_role_access(self):
        self.client.force_login(self.admin_user)
        res = self.client.get("/store/batches/", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Inventory &amp; Batches")
        self.assertContains(res, "BAT-AMOX-EARLY")

        res_detail = self.client.get(
            f"/store/batches/{self.batch_early.pk}/", HTTP_HOST="store.hms.test"
        )
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "BAT-AMOX-EARLY")
        self.assertContains(res_detail, "Stock Movement Ledger")

    def test_fefo_ordering_enforced(self):
        self.client.force_login(self.pharmacy_user)
        res = self.client.get("/store/batches/?q=Amoxicillin", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        batches = list(res.context["batches"])
        self.assertEqual(len(batches), 2)
        # FEFO order: batch_early (10 days) must precede batch_later (30 days)
        self.assertEqual(batches[0].pk, self.batch_early.pk)
        self.assertEqual(batches[1].pk, self.batch_later.pk)

    def test_status_filters(self):
        self.client.force_login(self.pharmacy_user)

        # Quarantined filter
        res = self.client.get("/store/batches/?status=quarantined", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "BAT-PCM-QRN")
        self.assertNotContains(res, "BAT-AMOX-EARLY")

        # Expired filter
        res = self.client.get("/store/batches/?status=expired", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "BAT-PCM-EXP")
        self.assertNotContains(res, "BAT-AMOX-EARLY")

        # Low stock filter
        res = self.client.get("/store/batches/?status=low_stock", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "BAT-PCM-LOW")
        self.assertNotContains(res, "BAT-AMOX-LATER")

    def test_search_by_batch_number_and_medicine(self):
        self.client.force_login(self.pharmacy_user)

        res = self.client.get("/store/batches/?q=BAT-PCM-LOW", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "BAT-PCM-LOW")
        self.assertNotContains(res, "BAT-AMOX-EARLY")

        res_med = self.client.get("/store/batches/?q=Dolo", HTTP_HOST="store.hms.test")
        self.assertEqual(res_med.status_code, 200)
        self.assertContains(res_med, "Paracetamol")

    def test_batch_detail_shows_movements(self):
        self.client.force_login(self.pharmacy_user)
        res = self.client.get(
            f"/store/batches/{self.batch_early.pk}/", HTTP_HOST="store.hms.test"
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "BAT-AMOX-EARLY")
        self.assertContains(res, "Receipt")
        self.assertContains(res, "stock_receipt")

    def test_stock_adjustment_from_detail(self):
        self.client.force_login(self.pharmacy_user)
        req_key = uuid.uuid4()
        initial_stock = self.batch_early.quantity_on_hand

        post_data = {
            "request_key": str(req_key),
            "quantity_delta": "-5.000",
            "reason": "Test stock breakage",
            "next": f"/store/batches/{self.batch_early.pk}/",
        }
        res = self.client.post(
            f"/pharmacy/batches/{self.batch_early.pk}/adjust/",
            post_data,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res, f"/store/batches/{self.batch_early.pk}/")

        self.batch_early.refresh_from_db()
        self.assertEqual(self.batch_early.quantity_on_hand, initial_stock - Decimal("5.000"))

        movement = StockMovement.objects.filter(request_key=req_key).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.kind, StockMovement.Kind.ADJUSTMENT)
        self.assertEqual(movement.quantity_delta, Decimal("-5.000"))

    def test_batch_quarantine_toggle_from_detail(self):
        self.client.force_login(self.pharmacy_user)
        req_key = uuid.uuid4()
        self.assertFalse(self.batch_early.is_quarantined)

        post_data = {
            "request_key": str(req_key),
            "is_quarantined": "true",
            "reason": "Quality check required",
            "next": f"/store/batches/{self.batch_early.pk}/",
        }
        res = self.client.post(
            f"/pharmacy/batches/{self.batch_early.pk}/quarantine/",
            post_data,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res, f"/store/batches/{self.batch_early.pk}/")

        self.batch_early.refresh_from_db()
        self.assertTrue(self.batch_early.is_quarantined)

    def test_negative_stock_adjustment_prevented(self):
        self.client.force_login(self.pharmacy_user)
        req_key = uuid.uuid4()
        post_data = {
            "request_key": str(req_key),
            "quantity_delta": "-999.000",
            "reason": "Excess deduction",
        }
        res = self.client.post(
            f"/pharmacy/batches/{self.batch_early.pk}/adjust/",
            post_data,
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "Adjustment cannot make stock negative", status_code=400)
