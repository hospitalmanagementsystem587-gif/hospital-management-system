from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Invoice, InvoiceLine, Patient, Price, Service, StaffProfile
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
class ServicePricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)
        configure_role_permissions()
        cls.today = date(2026, 10, 1)

        # Admin user
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user = User.objects.create_user(
            username="srvadmin", email="srvadmin@test.com", password="password"
        )
        cls.admin_user.groups.add(admin_group)
        cls.admin_staff = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM-SRV-01",
        )

        # Reception user
        reception_group = Group.objects.get(name="Reception")
        cls.reception_user = User.objects.create_user(
            username="srvreception", email="srvreception@test.com", password="password"
        )
        cls.reception_user.groups.add(reception_group)
        cls.reception_staff = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC-SRV-01",
        )

        cls.patient = Patient.objects.create(
            mrn="MRN-SRV-01",
            full_name="Anita Roy",
            phone="9876543210",
        )

        cls.service = Service.objects.create(
            code="SRV-PHYSIO",
            name="Physiotherapy Session",
            current_charge=Decimal("400.00"),
            is_active=False,
        )

    def test_fallback_to_current_charge_when_no_canonical_price_exists(self):
        """When no Price record exists, Service.get_current_price() returns legacy current_charge."""
        self.assertEqual(self.service.get_current_price(as_of=self.today), Decimal("400.00"))

    def test_canonical_price_overrides_current_charge_when_active_and_effective(self):
        """Approved and effective canonical Price takes precedence over current_charge."""
        price = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("650.00"),
            currency="INR",
            effective_from=self.today - timedelta(days=10),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        self.assertEqual(self.service.get_current_price(as_of=self.today), Decimal("650.00"))

    def test_effective_date_ranges_past_current_future(self):
        """Resolves historical, current, and future prices according to effective_from and effective_until."""
        past_date = self.today - timedelta(days=30)
        future_date = self.today + timedelta(days=30)

        # Past price: 500
        p_past = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("500.00"),
            currency="INR",
            effective_from=past_date,
            effective_until=self.today - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        # Current price: 700
        p_current = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("700.00"),
            currency="INR",
            effective_from=self.today,
            effective_until=future_date - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
            version=2,
        )
        # Future price: 900
        p_future = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("900.00"),
            currency="INR",
            effective_from=future_date,
            status=Price.Status.APPROVED,
            is_active=True,
            version=3,
        )

        self.assertEqual(self.service.get_current_price(as_of=past_date + timedelta(days=5)), Decimal("500.00"))
        self.assertEqual(self.service.get_current_price(as_of=self.today), Decimal("700.00"))
        self.assertEqual(self.service.get_current_price(as_of=future_date + timedelta(days=5)), Decimal("900.00"))

    def test_unapproved_or_inactive_canonical_prices_ignored(self):
        """Draft, pending, or inactive prices are ignored in get_current_price()."""
        Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("1200.00"),
            currency="INR",
            effective_from=self.today - timedelta(days=5),
            status=Price.Status.PENDING_APPROVAL,
            is_active=False,
        )
        # Should fallback to current_charge since canonical price is not approved
        self.assertEqual(self.service.get_current_price(as_of=self.today), Decimal("400.00"))

        Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("1500.00"),
            currency="INR",
            effective_from=self.today - timedelta(days=5),
            status=Price.Status.APPROVED,
            is_active=False,  # deactivated
            version=2,
        )
        self.assertEqual(self.service.get_current_price(as_of=self.today), Decimal("400.00"))

    def test_billing_selects_effective_canonical_service_price(self):
        """Invoice creation automatically picks the effective canonical service price when unit_price is omitted."""
        Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("550.00"),
            currency="INR",
            effective_from=self.today - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
        )

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
        self.assertEqual(invoice.lines.count(), 1)
        line = invoice.lines.first()
        self.assertEqual(line.unit_price, Decimal("550.00"))
        self.assertEqual(line.quantity, Decimal("2"))
        self.assertEqual(line.line_total, Decimal("1100.00"))
        self.assertEqual(invoice.total, Decimal("1100.00"))

    def test_historical_invoices_remain_unchanged_when_price_changes_or_deactivated(self):
        """Historical invoice lines are frozen and untouched by new price versions or deactivation."""
        # 1. Create first invoice at 550
        Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("550.00"),
            currency="INR",
            effective_from=self.today - timedelta(days=10),
            effective_until=self.today - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        invoice1 = Invoice.objects.create(
            patient=self.patient,
            number="INV-HIST-001",
            total=Decimal("550.00"),
            status=Invoice.Status.ISSUED,
        )
        line1 = InvoiceLine.objects.create(
            invoice=invoice1,
            service=self.service,
            description="Historical service",
            quantity=Decimal("1"),
            unit_price=Decimal("550.00"),
            line_total=Decimal("550.00"),
        )

        # 2. Add new price version: 800
        p2 = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("800.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.APPROVED,
            is_active=True,
            version=2,
        )

        # Historical invoice line must remain 550
        line1.refresh_from_db()
        invoice1.refresh_from_db()
        self.assertEqual(line1.unit_price, Decimal("550.00"))
        self.assertEqual(line1.line_total, Decimal("550.00"))
        self.assertEqual(invoice1.total, Decimal("550.00"))

        # Deactivate new price
        p2.is_active = False
        p2.save()

        line1.refresh_from_db()
        invoice1.refresh_from_db()
        self.assertEqual(line1.unit_price, Decimal("550.00"))
        self.assertEqual(line1.line_total, Decimal("550.00"))
        self.assertEqual(invoice1.total, Decimal("550.00"))
