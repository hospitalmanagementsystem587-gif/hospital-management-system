from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Invoice, InvoiceLine, Patient, Payment, PaymentMethod, Price, Refund, Service, StaffProfile
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
    ALLOWED_HOSTS=["*"],
)
class InvoicePriceSnapshotsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)
        configure_role_permissions()
        cls.today = date(2026, 10, 1)

        # Admin user
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user = User.objects.create_user(
            username="invadmin", email="invadmin@test.com", password="password", is_staff=True
        )
        cls.admin_user.groups.add(admin_group)
        cls.admin_staff = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM-INV-01",
        )

        # Reception user
        reception_group = Group.objects.get(name="Reception")
        cls.reception_user = User.objects.create_user(
            username="invreception", email="invreception@test.com", password="password"
        )
        cls.reception_user.groups.add(reception_group)
        cls.reception_staff = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC-INV-01",
        )

        cls.patient = Patient.objects.create(
            mrn="MRN-INV-01",
            full_name="Meena Kumari",
            phone="9876543213",
        )

        cls.payment_method = PaymentMethod.objects.create(
            code="CASH",
            name="Cash Payment",
        )

        cls.service = Service.objects.create(
            code="SRV-USG",
            name="Ultrasound Abdomen",
            current_charge=Decimal("1200.00"),
            is_active=True,
        )

    def test_invoice_creation_snapshots_price_immutably(self):
        """When an invoice is issued, InvoiceLine captures unit_price, quantity, and line_total immutably."""
        # 1. Establish canonical price at 1500
        p1 = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("1500.00"),
            currency="INR",
            effective_from=self.today - timedelta(days=10),
            status=Price.Status.APPROVED,
            is_active=True,
        )

        # 2. Issue invoice via reception staff
        self.client.force_login(self.reception_user)
        payload = {
            "patient": self.patient.pk,
            "service": self.service.pk,
            "quantity": "2",
        }
        response = self.client.post("/invoices/create/", data=payload, HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 302)

        invoice = Invoice.objects.filter(patient=self.patient).order_by("-id").first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        self.assertEqual(invoice.subtotal, Decimal("3000.00"))
        self.assertEqual(invoice.total, Decimal("3000.00"))

        line = invoice.lines.first()
        self.assertEqual(line.unit_price, Decimal("1500.00"))
        self.assertEqual(line.quantity, Decimal("2"))
        self.assertEqual(line.line_total, Decimal("3000.00"))

        # 3. Catalog price changes to 2200
        p1.effective_until = self.today - timedelta(days=1)
        p1.save()

        p2 = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("2200.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.APPROVED,
            is_active=True,
        )

        # Also modify legacy service.current_charge
        self.service.current_charge = Decimal("2200.00")
        self.service.save()

        # 4. Verify historical invoice and line are unchanged
        invoice.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(invoice.subtotal, Decimal("3000.00"))
        self.assertEqual(invoice.total, Decimal("3000.00"))
        self.assertEqual(line.unit_price, Decimal("1500.00"))
        self.assertEqual(line.line_total, Decimal("3000.00"))

    def test_payment_and_refund_workflows_reference_snapshotted_amounts(self):
        """Payment and refund operations strictly respect snapshotted invoice totals after price changes."""
        # 1. Create invoice directly with snapshotted line of 1000
        invoice = Invoice.objects.create(
            number="INV-SNAP-100",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("1000.00"),
            issued_at=timezone.now(),
            created_by=self.reception_staff,
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            service=self.service,
            description="Historical Ultrasound",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
            line_total=Decimal("1000.00"),
        )

        # 2. Add payment of 1000
        payment = Payment.objects.create(
            receipt_number="REC-SNAP-100",
            invoice=invoice,
            method=self.payment_method,
            amount=Decimal("1000.00"),
            received_at=timezone.now(),
            received_by=self.reception_staff,
        )

        # 3. New catalog price is now 2500
        Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("2500.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.APPROVED,
            is_active=True,
        )

        # 4. Perform refund of snapshotted payment
        self.client.force_login(self.admin_user)
        refund_payload = {
            "payment": payment.pk,
            "amount": "1000.00",
            "reason": "Patient requested cancellation before scan",
        }
        response = self.client.post(
            f"/invoices/{invoice.pk}/refunds/",
            data=refund_payload,
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)

        refund = Refund.objects.filter(payment=payment).first()
        self.assertIsNotNone(refund)
        self.assertEqual(refund.amount, Decimal("1000.00"))
        self.assertEqual(refund.status, Refund.Status.ISSUED)

        # 5. Over-refunding beyond the snapshotted payment balance fails
        response_excess = self.client.post(
            f"/invoices/{invoice.pk}/refunds/",
            data={"payment": payment.pk, "amount": "100.00", "reason": "Over-refund"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response_excess.status_code, 400)
