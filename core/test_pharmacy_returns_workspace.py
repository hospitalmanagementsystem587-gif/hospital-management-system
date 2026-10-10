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
    Invoice,
    Medicine,
    MedicineBatch,
    NumberSequence,
    Patient,
    Payment,
    PaymentMethod,
    PharmacyReturn,
    PharmacySale,
    PharmacySaleLine,
    Prescription,
    PrescriptionItem,
    ReturnLine,
    StaffProfile,
    StockReceipt,
    StockMovement,
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
class PharmacyReturnsWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        NumberSequence.objects.get_or_create(code="INVOICE", defaults={"prefix": "INV-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="PHARMACY_SALE", defaults={"prefix": "SALE-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="PHARMACY_RETURN", defaults={"prefix": "RET-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="DISPENSING", defaults={"prefix": "DISP-", "next_value": 1000})
        NumberSequence.objects.get_or_create(code="PRESCRIPTION", defaults={"prefix": "RX-", "next_value": 1000})
        configure_role_permissions()

        cls.pharmacy_user = User.objects.create_user("pharm_user_ret", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM-RET-1",
        )

        cls.reception_user = User.objects.create_user("rec_user_ret", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC-RET-1",
        )

        cls.admin_user = User.objects.create_user("admin_user_ret", password="password", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM-RET-1",
        )

        cls.doctor_user = User.objects.create_user("doc_user_ret", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-RET-1",
        )

        cls.patient = Patient.objects.create(
            mrn="PAT-RET-01",
            full_name="Return Patient",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 25),
            phone="+15550200",
        )

        cls.supplier = Supplier.objects.create(code="SUP-RET", name="Return Supplier Ltd")
        cls.receipt = StockReceipt.objects.create(
            number="REC-RET-100", supplier=cls.supplier, received_at=timezone.now()
        )

        cls.med_otc = Medicine.objects.create(
            code="MED-RET-OTC",
            generic_name="Paracetamol",
            brand_name="Calpol",
            strength="500mg",
            dosage_form="tablet",
            unit="tablet",
            is_otc=True,
            is_active=True,
        )

        cls.batch = MedicineBatch.objects.create(
            medicine=cls.med_otc,
            receipt=cls.receipt,
            batch_number="BAT-RET-01",
            expiry_date=timezone.localdate() + timedelta(days=90),
            quantity_received=Decimal("100.000"),
            quantity_on_hand=Decimal("50.000"),
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.50"),
            is_quarantined=False,
        )

        # Create OTC Sale & Line
        cls.sale_invoice = Invoice.objects.create(
            number="INV-RET-SALE",
            patient=None,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("25.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("25.00"),
            issued_at=timezone.now(),
            created_by=cls.pharmacy_profile,
        )
        cls.sale = PharmacySale.objects.create(
            number="SALE-RET-001",
            invoice=cls.sale_invoice,
            status=PharmacySale.Status.ISSUED,
            sold_at=timezone.now(),
            sold_by=cls.pharmacy_profile,
        )
        cls.sale_line = PharmacySaleLine.objects.create(
            sale=cls.sale,
            batch=cls.batch,
            quantity=Decimal("10.000"),
            unit_price=Decimal("2.50"),
            line_total=Decimal("25.00"),
        )

        # Create Prescription, Dispensing & Line
        cls.prescription = Prescription.objects.create(
            number="RX-RET-001",
            patient=cls.patient,
            doctor=cls.doctor_profile,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )
        cls.rx_item = PrescriptionItem.objects.create(
            prescription=cls.prescription,
            medicine=cls.med_otc,
            dosage="500mg",
            frequency="TID",
            duration="5 days",
            quantity=Decimal("15.000"),
        )
        cls.disp_invoice = Invoice.objects.create(
            number="INV-RET-DISP",
            patient=cls.patient,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("37.50"),
            tax_total=Decimal("0.00"),
            total=Decimal("37.50"),
            issued_at=timezone.now(),
            created_by=cls.pharmacy_profile,
        )
        cls.dispensing = Dispensing.objects.create(
            number="DISP-RET-001",
            prescription=cls.prescription,
            invoice=cls.disp_invoice,
            patient=cls.patient,
            dispensed_by=cls.pharmacy_profile,
            status=Dispensing.Status.COMPLETED,
            dispensed_at=timezone.now(),
        )
        cls.disp_line = DispensingLine.objects.create(
            dispensing=cls.dispensing,
            prescription_item=cls.rx_item,
            batch=cls.batch,
            quantity=Decimal("15.000"),
            unit_price=Decimal("2.50"),
        )

    def test_unauthorized_user_cannot_create_or_reject_returns(self):
        url_create = reverse("pharmacy_return_create")
        res = self.client.post(url_create, {}, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 302)

        self.client.force_login(self.doctor_user)
        res = self.client.post(url_create, {}, HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 403)

    def test_successful_return_request_for_otc_sale(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_return_create")
        req_key = str(uuid.uuid4())

        post_data = {
            "sale_line": self.sale_line.pk,
            "quantity": "4.000",
            "reason": "Customer overbought and returns sealed blister",
            "request_key": req_key,
        }

        res = self.client.post(url, post_data, HTTP_HOST="store.hms.test")
        self.assertRedirects(res, reverse("pharmacy_sale_detail", args=[self.sale.pk]))

        ret = PharmacyReturn.objects.latest("created_at")
        self.assertEqual(ret.status, PharmacyReturn.Status.PENDING)
        self.assertEqual(ret.reason, "Customer overbought and returns sealed blister")
        self.assertEqual(ret.created_by, self.pharmacy_profile)

        line = ret.lines.get()
        self.assertEqual(line.sale_line, self.sale_line)
        self.assertEqual(line.quantity, Decimal("4.000"))
        self.assertEqual(line.refund_amount, Decimal("10.00"))

        audit = AuditEvent.objects.filter(action="pharmacy.return_requested", target_id=str(ret.pk)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details.get("quantity"), "4.000")

    def test_successful_return_request_for_dispensed_prescription(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_return_create")
        req_key = str(uuid.uuid4())

        post_data = {
            "dispensing_line": self.disp_line.pk,
            "quantity": "5.000",
            "reason": "Doctor adjusted regimen",
            "request_key": req_key,
        }

        res = self.client.post(url, post_data, HTTP_HOST="store.hms.test")
        self.assertRedirects(res, reverse("pharmacy_prescription_list"))

        ret = PharmacyReturn.objects.latest("created_at")
        self.assertEqual(ret.patient, self.patient)
        self.assertEqual(ret.status, PharmacyReturn.Status.PENDING)

        line = ret.lines.get()
        self.assertEqual(line.dispensing_line, self.disp_line)
        self.assertEqual(line.quantity, Decimal("5.000"))
        self.assertEqual(line.refund_amount, Decimal("12.50"))

    def test_return_rejects_exceeding_unreturned_quantity_or_invalid_inputs(self):
        self.client.force_login(self.pharmacy_user)
        url = reverse("pharmacy_return_create")

        # Exceeds sale line quantity (original 10)
        res = self.client.post(
            url,
            {
                "sale_line": self.sale_line.pk,
                "quantity": "25.000",
                "reason": "Too much",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Return exceeds the unreturned transaction quantity", res.content.decode())

        # Missing reason
        res = self.client.post(
            url,
            {
                "sale_line": self.sale_line.pk,
                "quantity": "2.000",
                "reason": "",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)

        # Both sale_line and dispensing_line provided
        res = self.client.post(
            url,
            {
                "sale_line": self.sale_line.pk,
                "dispensing_line": self.disp_line.pk,
                "quantity": "2.000",
                "reason": "Ambiguous",
                "request_key": str(uuid.uuid4()),
            },
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 400)

    def test_financial_rejection_of_pending_return(self):
        ret = PharmacyReturn.objects.create(
            number="RET-REJ-001",
            patient=None,
            reason="Unopened box",
            status=PharmacyReturn.Status.PENDING,
            created_by=self.pharmacy_profile,
            request_key=uuid.uuid4(),
        )
        ReturnLine.objects.create(
            pharmacy_return=ret,
            sale_line=self.sale_line,
            quantity=Decimal("3.000"),
            refund_amount=Decimal("7.50"),
        )

        self.client.force_login(self.admin_user)
        url = reverse("pharmacy_return_reject", args=[ret.pk])
        res = self.client.post(url, {"reason": "Packaging is tampered"}, HTTP_HOST="staff.hms.test")
        self.assertRedirects(res, reverse("invoice_detail", args=[self.sale_invoice.pk]))

        ret.refresh_from_db()
        self.assertEqual(ret.status, PharmacyReturn.Status.REJECTED)

        audit = AuditEvent.objects.filter(action="pharmacy.return_rejected", target_id=str(ret.pk)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details.get("reason"), "Packaging is tampered")

    def test_approved_refund_restores_stock_with_traceable_movement(self):
        method = PaymentMethod.objects.create(name="Cash", code="CASH", is_active=True)
        payment = Payment.objects.create(
            receipt_number="PAY-RET-001",
            invoice=self.sale_invoice,
            method=method,
            amount=Decimal("25.00"),
            received_by=self.pharmacy_profile,
            received_at=timezone.now(),
        )
        pharmacy_return = PharmacyReturn.objects.create(
            number="RET-APPROVE-001",
            reason="Sealed pack returned",
            status=PharmacyReturn.Status.PENDING,
            created_by=self.pharmacy_profile,
            request_key=uuid.uuid4(),
        )
        ReturnLine.objects.create(
            pharmacy_return=pharmacy_return,
            sale_line=self.sale_line,
            quantity=Decimal("2.000"),
            refund_amount=Decimal("5.00"),
        )
        before = self.batch.quantity_on_hand

        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("invoice_refund", args=[self.sale_invoice.pk]),
            {
                "payment": payment.pk,
                "pharmacy_return": pharmacy_return.pk,
                "amount": "5.00",
                "reason": "Approved sealed return",
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        pharmacy_return.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(pharmacy_return.status, PharmacyReturn.Status.APPROVED)
        self.assertEqual(self.batch.quantity_on_hand, before + Decimal("2.000"))
        movement = StockMovement.objects.get(
            kind=StockMovement.Kind.RETURN,
            reference_id=str(pharmacy_return.pk),
        )
        self.assertEqual(movement.quantity_delta, Decimal("2.000"))
