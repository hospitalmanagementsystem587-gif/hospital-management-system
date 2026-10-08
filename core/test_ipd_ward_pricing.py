from datetime import date, datetime, timedelta, time
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Admission, Bed, Invoice, InvoiceLine, Patient, Price, StaffProfile, Ward
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
class IPDWardPricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)
        configure_role_permissions()
        cls.today = date(2026, 10, 1)

        # Doctor user
        doc_group = Group.objects.get(name="Doctor")
        cls.doc_user = User.objects.create_user(
            username="ipddoc", email="ipddoc@test.com", password="password"
        )
        cls.doc_user.groups.add(doc_group)
        cls.doctor = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-IPD-01",
        )

        cls.patient = Patient.objects.create(
            mrn="MRN-IPD-01",
            full_name="Sunil Mehta",
            phone="9876543212",
        )

        cls.ward = Ward.objects.create(
            code="ICU_WARD",
            name="Intensive Care Unit",
            category=Ward.Category.ICU,
            daily_rate=Decimal("2500.00"),
            is_active=True,
        )
        cls.bed = Bed.objects.create(
            ward=cls.ward,
            bed_number="ICU-01",
            status=Bed.Status.OCCUPIED,
        )

    def test_fallback_to_ward_daily_rate_when_no_canonical_price_exists(self):
        """When no canonical Price exists, Ward.get_current_price() returns legacy daily_rate."""
        self.assertEqual(self.ward.get_current_price(as_of=self.today), Decimal("2500.00"))

    def test_effective_dated_ward_pricing_past_current_future(self):
        """Resolves historical, current, and future ward rates based on effective dates."""
        past_date = self.today - timedelta(days=60)
        future_date = self.today + timedelta(days=30)

        # Past price: 2800
        Price.objects.create(
            price_type=Price.PriceType.WARD,
            item=self.ward,
            amount=Decimal("2800.00"),
            currency="INR",
            effective_from=past_date,
            effective_until=self.today - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        # Current price: 3500
        Price.objects.create(
            price_type=Price.PriceType.WARD,
            item=self.ward,
            amount=Decimal("3500.00"),
            currency="INR",
            effective_from=self.today,
            effective_until=future_date - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        # Future price: 4200
        Price.objects.create(
            price_type=Price.PriceType.WARD,
            item=self.ward,
            amount=Decimal("4200.00"),
            currency="INR",
            effective_from=future_date,
            status=Price.Status.APPROVED,
            is_active=True,
        )

        self.assertEqual(self.ward.get_current_price(as_of=past_date + timedelta(days=10)), Decimal("2800.00"))
        self.assertEqual(self.ward.get_current_price(as_of=self.today), Decimal("3500.00"))
        self.assertEqual(self.ward.get_current_price(as_of=future_date + timedelta(days=10)), Decimal("4200.00"))

    def test_admission_rate_selection_at_admission_date(self):
        """Admission estimated bed charges use the rate in effect as of the admission date."""
        past_date = self.today - timedelta(days=20)
        # Old rate 3000
        Price.objects.create(
            price_type=Price.PriceType.WARD,
            item=self.ward,
            amount=Decimal("3000.00"),
            currency="INR",
            effective_from=past_date,
            effective_until=self.today - timedelta(days=1),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        # Current rate 4000 starting today
        Price.objects.create(
            price_type=Price.PriceType.WARD,
            item=self.ward,
            amount=Decimal("4000.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.APPROVED,
            is_active=True,
        )

        admission_time = timezone.make_aware(datetime.combine(past_date, time(10, 0)))
        discharge_time = timezone.make_aware(datetime.combine(past_date + timedelta(days=5), time(12, 0)))

        adm = Admission.objects.create(
            admission_number="ADM-IPD-001",
            patient=self.patient,
            bed=self.bed,
            admitting_doctor=self.doctor,
            status=Admission.Status.DISCHARGED,
            admission_reason="Acute Respiratory Distress",
            admitted_at=admission_time,
            discharged_at=discharge_time,
        )
        # 6 days stayed at rate 3000 = 18000
        self.assertEqual(adm.total_days_stayed, 6)
        self.assertEqual(adm.estimated_bed_charges, Decimal("18000.00"))

    def test_historical_admissions_and_invoices_remain_unchanged(self):
        """Later ward rate updates do not alter historical admission calculations or invoices."""
        admission_time = timezone.make_aware(datetime.combine(self.today - timedelta(days=10), time(9, 0)))
        discharge_time = timezone.make_aware(datetime.combine(self.today - timedelta(days=8), time(11, 0)))

        adm = Admission.objects.create(
            admission_number="ADM-IPD-002",
            patient=self.patient,
            bed=self.bed,
            admitting_doctor=self.doctor,
            status=Admission.Status.DISCHARGED,
            admission_reason="Cardiac Monitoring",
            admitted_at=admission_time,
            discharged_at=discharge_time,
        )
        # 3 days at fallback daily_rate (2500) = 7500
        self.assertEqual(adm.estimated_bed_charges, Decimal("7500.00"))

        # Issue historical invoice
        invoice = Invoice.objects.create(
            patient=self.patient,
            number="INV-IPD-001",
            total=Decimal("7500.00"),
            status=Invoice.Status.ISSUED,
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            description=f"IPD Bed charges for {adm.admission_number}",
            quantity=Decimal("3"),
            unit_price=Decimal("2500.00"),
            line_total=Decimal("7500.00"),
        )

        # Now approve a new ward price of 5000 effective today
        Price.objects.create(
            price_type=Price.PriceType.WARD,
            item=self.ward,
            amount=Decimal("5000.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.APPROVED,
            is_active=True,
        )

        # Verify historical admission and invoice are untouched
        self.assertEqual(adm.estimated_bed_charges, Decimal("7500.00"))
        invoice.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("2500.00"))
        self.assertEqual(line.line_total, Decimal("7500.00"))
        self.assertEqual(invoice.total, Decimal("7500.00"))
