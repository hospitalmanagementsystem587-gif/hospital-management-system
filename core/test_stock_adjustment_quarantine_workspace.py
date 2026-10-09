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
class StockAdjustmentQuarantineWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        configure_role_permissions()

        cls.pharmacy_user = User.objects.create_user("pharm_user_adj", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM-ADJ-1",
        )

        cls.doctor_user = User.objects.create_user("doc_user_adj", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-ADJ-1",
        )

        cls.supplier = Supplier.objects.create(code="SUP-ADJ", name="Adjustment Supplier")
        cls.receipt = StockReceipt.objects.create(
            number="REC-ADJ-100", supplier=cls.supplier, received_at=timezone.now()
        )

        cls.medicine = Medicine.objects.create(
            code="MED-ADJ-001",
            generic_name="Amoxicillin",
            brand_name="Mox",
            strength="500mg",
            dosage_form="capsule",
            unit="capsule",
            is_otc=False,
            is_active=True,
        )

        cls.batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            receipt=cls.receipt,
            batch_number="BAT-ADJ-01",
            expiry_date=timezone.localdate() + timedelta(days=120),
            quantity_received=Decimal("100.000"),
            quantity_on_hand=Decimal("50.000"),
            purchase_price=Decimal("1.50"),
            sale_price=Decimal("3.00"),
            is_quarantined=False,
        )

    def test_unauthorized_access_prevented(self):
        url_adj = reverse("stock_adjustment", args=[self.batch.pk])
        res = self.client.post(url_adj, {}, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 302)

        self.client.force_login(self.doctor_user)
        res = self.client.post(url_adj, {}, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 403)

        url_quar = reverse("batch_quarantine", args=[self.batch.pk])
        res = self.client.post(url_quar, {}, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 403)

    def test_positive_and_negative_stock_adjustment_creates_movement_and_audit(self):
        self.client.force_login(self.pharmacy_user)
        url_adj = reverse("stock_adjustment", args=[self.batch.pk])

        # Positive adjustment (+10)
        req_key_1 = str(uuid.uuid4())
        res1 = self.client.post(
            url_adj,
            {
                "quantity_delta": "10.000",
                "reason": "Physical count surplus found",
                "request_key": req_key_1,
                "next": reverse("batch_detail", args=[self.batch.pk]),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res1, reverse("batch_detail", args=[self.batch.pk]))

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_on_hand, Decimal("60.000"))

        mvt1 = StockMovement.objects.get(request_key=req_key_1)
        self.assertEqual(mvt1.kind, StockMovement.Kind.ADJUSTMENT)
        self.assertEqual(mvt1.quantity_delta, Decimal("10.000"))
        self.assertEqual(mvt1.quantity_before, Decimal("50.000"))
        self.assertEqual(mvt1.quantity_after, Decimal("60.000"))

        audit1 = AuditEvent.objects.get(action="stock.adjusted", target_id=str(self.batch.pk), details__reason="Physical count surplus found")
        self.assertEqual(audit1.actor, self.pharmacy_profile)

        # Negative adjustment (-5)
        req_key_2 = str(uuid.uuid4())
        res2 = self.client.post(
            url_adj,
            {
                "quantity_delta": "-5.000",
                "reason": "Damaged unit discarded",
                "request_key": req_key_2,
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res2, reverse("pharmacy_prescription_list"))

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_on_hand, Decimal("55.000"))

    def test_adjustment_cannot_make_stock_negative_and_requires_reason(self):
        self.client.force_login(self.pharmacy_user)
        url_adj = reverse("stock_adjustment", args=[self.batch.pk])

        # Excessive negative adjustment
        res = self.client.post(
            url_adj,
            {
                "quantity_delta": "-999.000",
                "reason": "Excess deduction",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot make stock negative", res.content.decode())

        # Missing reason
        res = self.client.post(
            url_adj,
            {
                "quantity_delta": "5.000",
                "reason": "",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)

        # Zero delta
        res = self.client.post(
            url_adj,
            {
                "quantity_delta": "0.000",
                "reason": "Zero delta",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)

    def test_batch_quarantine_and_release_workflows(self):
        self.client.force_login(self.pharmacy_user)
        url_quar = reverse("batch_quarantine", args=[self.batch.pk])

        # Quarantine batch
        req_key_q = str(uuid.uuid4())
        res_q = self.client.post(
            url_quar,
            {
                "is_quarantined": "true",
                "reason": "Suspected packaging discoloration",
                "request_key": req_key_q,
                "next": reverse("batch_detail", args=[self.batch.pk]),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res_q, reverse("batch_detail", args=[self.batch.pk]))

        self.batch.refresh_from_db()
        self.assertTrue(self.batch.is_quarantined)

        audit_q = AuditEvent.objects.filter(action="stock.quarantined", target_id=str(self.batch.pk)).first()
        self.assertIsNotNone(audit_q)
        self.assertEqual(audit_q.details.get("reason"), "Suspected packaging discoloration")

        # Release batch
        req_key_r = str(uuid.uuid4())
        res_r = self.client.post(
            url_quar,
            {
                "is_quarantined": "false",
                "reason": "Lab analysis cleared batch for dispensing",
                "request_key": req_key_r,
                "next": reverse("batch_detail", args=[self.batch.pk]),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res_r, reverse("batch_detail", args=[self.batch.pk]))

        self.batch.refresh_from_db()
        self.assertFalse(self.batch.is_quarantined)

        audit_r = AuditEvent.objects.filter(action="stock.quarantine_released", target_id=str(self.batch.pk)).first()
        self.assertIsNotNone(audit_r)
        self.assertEqual(audit_r.details.get("reason"), "Lab analysis cleared batch for dispensing")

    def test_idempotency_for_adjustment_and_quarantine(self):
        self.client.force_login(self.pharmacy_user)
        url_adj = reverse("stock_adjustment", args=[self.batch.pk])
        req_key = str(uuid.uuid4())

        post_data = {
            "quantity_delta": "3.000",
            "reason": "Inventory check",
            "request_key": req_key,
        }

        res1 = self.client.post(url_adj, post_data, HTTP_HOST="store.hms.test")
        self.assertEqual(res1.status_code, 302)

        res2 = self.client.post(url_adj, post_data, HTTP_HOST="store.hms.test")
        self.assertEqual(res2.status_code, 302)

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_on_hand, Decimal("53.000"))
        self.assertEqual(StockMovement.objects.filter(request_key=req_key).count(), 1)
