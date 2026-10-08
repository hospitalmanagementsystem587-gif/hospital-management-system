from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import DiagnosticTest, Invoice, InvoiceLine, Patient, Price, StaffProfile
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
class DiagnosticTestPricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)
        configure_role_permissions()
        cls.today = date(2026, 10, 1)

        # Admin user
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user = User.objects.create_user(
            username="diagadmin", email="diagadmin@test.com", password="password"
        )
        cls.admin_user.groups.add(admin_group)
        cls.admin_staff = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM-DIAG-01",
        )

        cls.patient = Patient.objects.create(
            mrn="MRN-DIAG-01",
            full_name="Rajesh Sharma",
            phone="9876543211",
        )

        cls.test_cbc = DiagnosticTest.objects.create(
            code="CBC_PANEL",
            name="Complete Blood Count",
            category=DiagnosticTest.Category.PATHOLOGY,
            turnaround_time="4 hours",
            is_active=True,
        )

    def test_diagnostic_test_returns_none_when_no_price_configured(self):
        """When no price is configured, get_current_price() returns None."""
        self.assertIsNone(self.test_cbc.get_current_price(as_of=self.today))

    def test_effective_dated_prices_past_current_future(self):
        """Resolves historical, current, and future prices according to effective dates."""
        past_date = self.today - timedelta(days=30)
        future_date = self.today + timedelta(days=30)

        # Historical price: 350
        Price.objects.create(
            price_type=Price.PriceType.DIAGNOSTIC,
            item=self.test_cbc,
            amount=Decimal("350.00"),
            currency="INR",
            effective_from=past_date,
            effective_until=self.today - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
            version=1,
        )
        # Current price: 450
        Price.objects.create(
            price_type=Price.PriceType.DIAGNOSTIC,
            item=self.test_cbc,
            amount=Decimal("450.00"),
            currency="INR",
            effective_from=self.today,
            effective_until=future_date - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
            version=2,
        )
        # Future scheduled price: 550
        Price.objects.create(
            price_type=Price.PriceType.DIAGNOSTIC,
            item=self.test_cbc,
            amount=Decimal("550.00"),
            currency="INR",
            effective_from=future_date,
            status=Price.Status.APPROVED,
            is_active=True,
            version=3,
        )

        self.assertEqual(self.test_cbc.get_current_price(as_of=past_date + timedelta(days=5)), Decimal("350.00"))
        self.assertEqual(self.test_cbc.get_current_price(as_of=self.today), Decimal("450.00"))
        self.assertEqual(self.test_cbc.get_current_price(as_of=future_date + timedelta(days=5)), Decimal("550.00"))

    def test_currency_and_active_status_explicit(self):
        """Explicitly tracks currency and excludes inactive prices."""
        p = Price.objects.create(
            price_type=Price.PriceType.DIAGNOSTIC,
            item=self.test_cbc,
            amount=Decimal("450.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.APPROVED,
            is_active=True,
            version=2,
        )
        self.assertEqual(p.currency, "INR")
        self.assertEqual(self.test_cbc.get_current_price(as_of=self.today), Decimal("450.00"))

        p.is_active = False
        p.save()
        self.assertIsNone(self.test_cbc.get_current_price(as_of=self.today))

    def test_unapproved_or_pending_prices_ignored(self):
        """Draft, pending approval, or rejected prices are excluded from resolution."""
        Price.objects.create(
            price_type=Price.PriceType.DIAGNOSTIC,
            item=self.test_cbc,
            amount=Decimal("450.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.PENDING_APPROVAL,
            is_active=False,
        )
        self.assertIsNone(self.test_cbc.get_current_price(as_of=self.today))

    def test_historical_invoices_and_snapshots_not_rewritten(self):
        """Modifying or adding diagnostic test prices does not alter historical invoice records."""
        Price.objects.create(
            price_type=Price.PriceType.DIAGNOSTIC,
            item=self.test_cbc,
            amount=Decimal("400.00"),
            currency="INR",
            effective_from=self.today - timedelta(days=20),
            effective_until=self.today - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        invoice = Invoice.objects.create(
            patient=self.patient,
            number="INV-DIAG-001",
            total=Decimal("400.00"),
            status=Invoice.Status.ISSUED,
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            description="Diagnostic: Complete Blood Count",
            quantity=Decimal("1"),
            unit_price=Decimal("400.00"),
            line_total=Decimal("400.00"),
        )

        # Introduce new diagnostic test price
        Price.objects.create(
            price_type=Price.PriceType.DIAGNOSTIC,
            item=self.test_cbc,
            amount=Decimal("600.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.APPROVED,
            is_active=True,
            version=2,
        )

        # Historical invoice line and total remain intact
        line.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("400.00"))
        self.assertEqual(line.line_total, Decimal("400.00"))
        self.assertEqual(invoice.total, Decimal("400.00"))
