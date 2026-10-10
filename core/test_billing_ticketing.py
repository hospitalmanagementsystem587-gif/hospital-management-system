from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Department,
    Invoice,
    Patient,
    PatientAccount,
    Payment,
    PaymentMethod,
    StaffProfile,
    Ticket,
)
from core.roles import configure_role_permissions
from core.services.ticketing import (
    create_patient_ticket,
    create_staff_ticket,
)

User = get_user_model()


class BillingTicketingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.dept_billing = Department.objects.create(name="Billing Dept", code="BILLING_DEPT")
        cls.dept_cardio = Department.objects.create(name="Cardiology Dept", code="CARDIO_DEPT")

        # Reception / Cashier staff user
        cls.reception_user = User.objects.create_user(
            username="reception_clerk", email="recep@hospital.com", password="password123"
        )
        recep_group = Group.objects.get(name="Reception")
        cls.reception_user.groups.add(recep_group)
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC-BILL-01",
            department=cls.dept_billing,
            job_title="Cashier",
        )

        # Doctor staff user
        cls.doc_user = User.objects.create_user(
            username="doc_billing_test", email="doc@hospital.com", password="password123"
        )
        doc_group = Group.objects.get(name="Doctor")
        cls.doc_user.groups.add(doc_group)
        cls.doc_profile = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-BILL-01",
            department=cls.dept_cardio,
            job_title="Cardiologist",
        )

        # Patients
        cls.patient_alice = Patient.objects.create(
            mrn="PAT-ALICE-BILL",
            full_name="Alice Billing Test",
        )
        cls.user_alice = User.objects.create_user(
            username="alice_patient", email="alice@test.com", password="password123"
        )
        PatientAccount.objects.create(
            user=cls.user_alice,
            patient=cls.patient_alice,
            is_verified=True,
        )

        cls.patient_bob = Patient.objects.create(
            mrn="PAT-BOB-BILL",
            full_name="Bob Billing Test",
        )
        cls.user_bob = User.objects.create_user(
            username="bob_patient", email="bob@test.com", password="password123"
        )
        PatientAccount.objects.create(
            user=cls.user_bob,
            patient=cls.patient_bob,
            is_verified=True,
        )

        cls.pay_method = PaymentMethod.objects.create(name="UPI / QR", code="UPI")

        # Alice's invoice and payment
        cls.alice_invoice = Invoice.objects.create(
            patient=cls.patient_alice,
            number="INV-ALICE-95",
            subtotal=Decimal("1200.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("1200.00"),
            status=Invoice.Status.ISSUED,
            issued_at=timezone.now(),
        )
        cls.alice_payment = Payment.objects.create(
            invoice=cls.alice_invoice,
            receipt_number="RCP-ALICE-95",
            amount=Decimal("1200.00"),
            method=cls.pay_method,
            received_at=timezone.now(),
        )

        # Bob's invoice (cross-patient)
        cls.bob_invoice = Invoice.objects.create(
            patient=cls.patient_bob,
            number="INV-BOB-95",
            subtotal=Decimal("5000.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("5000.00"),
            status=Invoice.Status.ISSUED,
            issued_at=timezone.now(),
        )

    def setUp(self):
        self.client = Client()

    def test_reception_can_create_billing_ticket_for_invoice(self):
        self.client.force_login(self.reception_user)
        resp = self.client.post(
            reverse("staff_ticket_create"),
            {
                "title": "Dispute on consultation line item charge",
                "category": Ticket.Category.BILLING,
                "priority": Ticket.Priority.NORMAL,
                "assigned_team": self.dept_billing.pk,
                "patient": self.patient_alice.pk,
                "invoice": self.alice_invoice.pk,
                "description": "Patient requested review of discount calculation on invoice INV-ALICE-95.",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        ticket = Ticket.objects.filter(title="Dispute on consultation line item charge").first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.category, Ticket.Category.BILLING)
        self.assertEqual(ticket.patient, self.patient_alice)
        self.assertEqual(ticket.assigned_team, self.dept_billing)

    def test_cross_patient_invoice_reference_rejected(self):
        # Alice tries to create ticket with Bob's invoice
        with self.assertRaises(ValidationError) as ctx:
            create_patient_ticket(
                patient=self.patient_alice,
                user=self.user_alice,
                title="Inquire on wrong invoice",
                description="Testing invoice ownership",
                category=Ticket.Category.BILLING,
                invoice=self.bob_invoice,
            )
        self.assertIn("invoice", ctx.exception.message_dict)

    def test_cross_patient_invoice_in_staff_ticket_rejected(self):
        # Staff specifies Alice as patient but attaches Bob's invoice
        with self.assertRaises(ValidationError) as ctx:
            create_staff_ticket(
                user=self.reception_user,
                title="Mismatched patient invoice",
                description="Description",
                category=Ticket.Category.BILLING,
                patient=self.patient_alice,
                invoice=self.bob_invoice,
            )
        self.assertIn("invoice", ctx.exception.message_dict)

    def test_draft_invoice_reference_rejected_for_patient(self):
        draft_invoice = Invoice.objects.create(
            patient=self.patient_alice,
            number="INV-DRAFT-ALICE",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            status=Invoice.Status.DRAFT,
        )
        with self.assertRaises(ValidationError) as ctx:
            create_patient_ticket(
                patient=self.patient_alice,
                user=self.user_alice,
                title="Draft inquiry",
                description="Testing draft invoice rejection",
                category=Ticket.Category.BILLING,
                invoice=draft_invoice,
            )
        self.assertIn("invoice", ctx.exception.message_dict)

    def test_patient_portal_invoice_detail_has_raise_ticket_link(self):
        self.client.force_login(self.user_alice)
        resp = self.client.get(
            f"/invoices/{self.alice_invoice.pk}/",
            HTTP_HOST="patient.localhost",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"invoice_id={self.alice_invoice.pk}")

    def test_staff_invoice_detail_has_raise_ticket_link(self):
        self.client.force_login(self.reception_user)
        resp = self.client.get(reverse("invoice_detail", args=[self.alice_invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("staff_ticket_create"))
        self.assertContains(resp, f"invoice_id={self.alice_invoice.pk}")
