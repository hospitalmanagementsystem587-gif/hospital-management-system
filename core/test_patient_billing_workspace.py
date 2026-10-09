from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Adjustment,
    Invoice,
    InvoiceLine,
    Patient,
    PatientAccount,
    Payment,
    PaymentMethod,
    Refund,
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
class PatientBillingWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Patient 1: Alice (verified)
        cls.alice_user = User.objects.create_user(
            "alice_billing",
            email="alice@example.com",
            password="Password123!",
            first_name="Alice",
            last_name="Gupta",
        )
        cls.alice_patient = Patient.objects.create(
            mrn="MRN-ALICE-BILL-01",
            full_name="Alice Gupta",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 28),
            phone="9876543210",
            email="alice@example.com",
        )
        cls.alice_account = PatientAccount.objects.create(
            user=cls.alice_user,
            patient=cls.alice_patient,
            is_verified=True,
        )

        # Patient 2: Bob (verified)
        cls.bob_user = User.objects.create_user(
            "bob_billing",
            email="bob@example.com",
            password="Password123!",
            first_name="Bob",
            last_name="Verma",
        )
        cls.bob_patient = Patient.objects.create(
            mrn="MRN-BOB-BILL-01",
            full_name="Bob Verma",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 32),
            phone="9876543211",
            email="bob@example.com",
        )
        cls.bob_account = PatientAccount.objects.create(
            user=cls.bob_user,
            patient=cls.bob_patient,
            is_verified=True,
        )

        cls.method = PaymentMethod.objects.create(name="UPI", code="UPI", is_active=True)

        # Alice Invoice 1: Issued, partially paid, with adjustment
        cls.alice_inv_partial = Invoice.objects.create(
            patient=cls.alice_patient,
            number="INV-ALICE-001",
            subtotal=Decimal("1500.00"),
            discount_total=Decimal("100.00"),
            tax_total=Decimal("50.00"),
            total=Decimal("1450.00"),
            status=Invoice.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=2),
        )
        InvoiceLine.objects.create(
            invoice=cls.alice_inv_partial,
            description="Consultation Consultation General",
            quantity=1,
            unit_price=Decimal("1000.00"),
            discount_amount=Decimal("100.00"),
            line_total=Decimal("900.00"),
        )
        InvoiceLine.objects.create(
            invoice=cls.alice_inv_partial,
            description="Diagnostic Lab CBC Test",
            quantity=1,
            unit_price=Decimal("500.00"),
            discount_amount=Decimal("0.00"),
            line_total=Decimal("500.00"),
        )
        cls.alice_payment = Payment.objects.create(
            invoice=cls.alice_inv_partial,
            receipt_number="RCP-ALICE-001",
            amount=Decimal("500.00"),
            method=cls.method,
            received_at=timezone.now() - timedelta(days=2),
        )
        Adjustment.objects.create(
            invoice=cls.alice_inv_partial,
            amount=Decimal("-50.00"),
            reason="Courtesy discount",
        )

        # Alice Invoice 2: Settled
        cls.alice_inv_settled = Invoice.objects.create(
            patient=cls.alice_patient,
            number="INV-ALICE-002",
            subtotal=Decimal("300.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("300.00"),
            status=Invoice.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=5),
        )
        Payment.objects.create(
            invoice=cls.alice_inv_settled,
            receipt_number="RCP-ALICE-002",
            amount=Decimal("300.00"),
            method=cls.method,
            received_at=timezone.now() - timedelta(days=5),
        )

        # Alice Invoice 3: Draft (must NOT appear in patient list or detail)
        cls.alice_inv_draft = Invoice.objects.create(
            patient=cls.alice_patient,
            number="INV-ALICE-DRAFT",
            subtotal=Decimal("700.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("700.00"),
            status=Invoice.Status.DRAFT,
        )

        # Bob Invoice (cross-patient)
        cls.bob_inv = Invoice.objects.create(
            patient=cls.bob_patient,
            number="INV-BOB-001",
            subtotal=Decimal("2000.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("2000.00"),
            status=Invoice.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=1),
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_anonymous_redirects_to_login(self):
        resp_list = self.client.get("/invoices/")
        self.assertEqual(resp_list.status_code, 302)
        self.assertIn("/accounts/login/", resp_list.url)

        resp_detail = self.client.get(f"/invoices/{self.alice_inv_partial.pk}/")
        self.assertEqual(resp_detail.status_code, 302)
        self.assertIn("/accounts/login/", resp_detail.url)

    def test_unverified_patient_cannot_view_invoices(self):
        self.alice_account.is_verified = False
        self.alice_account.save(update_fields=["is_verified"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/invoices/")
        self.assertEqual(resp.status_code, 403)

        resp_detail = self.client.get(f"/invoices/{self.alice_inv_partial.pk}/")
        self.assertEqual(resp_detail.status_code, 403)

    def test_archived_patient_cannot_view_invoices(self):
        self.alice_patient.archived_at = timezone.now()
        self.alice_patient.save(update_fields=["archived_at"])

        self.client.force_login(self.alice_user)
        resp = self.client.get("/invoices/")
        self.assertEqual(resp.status_code, 403)

    def test_invoice_list_shows_issued_and_excludes_draft_and_other_patients(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get("/invoices/")
        self.assertEqual(resp.status_code, 200)

        # Alice's issued invoices are visible
        self.assertContains(resp, "INV-ALICE-001")
        self.assertContains(resp, "INV-ALICE-002")
        self.assertContains(resp, "1450.00")
        self.assertContains(resp, "300.00")

        # Draft invoice must not appear
        self.assertNotContains(resp, "INV-ALICE-DRAFT")

        # Bob's invoice must not leak
        self.assertNotContains(resp, "INV-BOB-001")

    def test_invoice_filter_and_search(self):
        self.client.force_login(self.alice_user)

        # Filter by search term
        resp_q = self.client.get("/invoices/?q=001")
        self.assertEqual(resp_q.status_code, 200)
        self.assertContains(resp_q, "INV-ALICE-001")
        self.assertNotContains(resp_q, "INV-ALICE-002")

        # Filter by status
        resp_status = self.client.get("/invoices/?status=issued")
        self.assertEqual(resp_status.status_code, 200)
        self.assertContains(resp_status, "INV-ALICE-001")

    def test_invoice_detail_view_success_and_ledger_elements(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get(f"/invoices/{self.alice_inv_partial.pk}/")
        self.assertEqual(resp.status_code, 200)

        # Metadata & Totals
        self.assertContains(resp, "INV-ALICE-001")
        self.assertContains(resp, "1450.00")
        self.assertContains(resp, "1500.00")  # subtotal

        # Line items
        self.assertContains(resp, "Consultation Consultation General")
        self.assertContains(resp, "Diagnostic Lab CBC Test")

        # Payments & Receipts
        self.assertContains(resp, "RCP-ALICE-001")
        self.assertContains(resp, "500.00")

        # Adjustments
        self.assertContains(resp, "Courtesy discount")
        self.assertContains(resp, "-50.00")

        # Outstanding balance: 1450.00 - 50.00(adj) - 500.00(paid) = 900.00
        self.assertContains(resp, "900.00")

    def test_draft_invoice_detail_returns_404(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get(f"/invoices/{self.alice_inv_draft.pk}/")
        self.assertEqual(resp.status_code, 404)

    def test_cross_patient_invoice_detail_returns_404(self):
        self.client.force_login(self.alice_user)
        resp = self.client.get(f"/invoices/{self.bob_inv.pk}/")
        self.assertEqual(resp.status_code, 404)
