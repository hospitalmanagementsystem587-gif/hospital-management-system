from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from core.models import Price, Service
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
class PriceVersionsAndEffectiveDatesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.service = Service.objects.create(
            code="SRV_MRI_BRAIN",
            name="Brain MRI with Contrast",
            current_charge=Decimal("4500.00"),
        )
        cls.srv_ct = ContentType.objects.get_for_model(cls.service)

        # Historical (expired) price: T - 60 to T - 31
        cls.p_expired = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            content_type=cls.srv_ct,
            object_id=cls.service.pk,
            scope="standard",
            amount=Decimal("4000.00"),
            currency="INR",
            effective_from=date.today() - timedelta(days=60),
            effective_until=date.today() - timedelta(days=31),
            status=Price.Status.APPROVED,
            is_active=True,
            version=1,
        )

        # Current price: T - 30 to T + 30
        cls.p_current = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            content_type=cls.srv_ct,
            object_id=cls.service.pk,
            scope="standard",
            amount=Decimal("4500.00"),
            currency="INR",
            effective_from=date.today() - timedelta(days=30),
            effective_until=date.today() + timedelta(days=30),
            status=Price.Status.APPROVED,
            is_active=True,
            version=2,
        )

        # Future price: T + 31 onwards
        cls.p_future = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            content_type=cls.srv_ct,
            object_id=cls.service.pk,
            scope="standard",
            amount=Decimal("5000.00"),
            currency="INR",
            effective_from=date.today() + timedelta(days=31),
            effective_until=None,
            status=Price.Status.APPROVED,
            is_active=True,
            version=3,
        )

    def test_current_price_resolution_as_of_today(self):
        """Today resolves to the currently effective price version."""
        today_price = Price.get_current_price(self.service, as_of=date.today())
        self.assertIsNotNone(today_price)
        self.assertEqual(today_price.pk, self.p_current.pk)
        self.assertEqual(today_price.amount, Decimal("4500.00"))

    def test_historical_price_resolution_in_past(self):
        """Querying at a historical date resolves the expired price effective then."""
        past_date = date.today() - timedelta(days=45)
        past_price = Price.get_current_price(self.service, as_of=past_date)
        self.assertIsNotNone(past_price)
        self.assertEqual(past_price.pk, self.p_expired.pk)
        self.assertEqual(past_price.amount, Decimal("4000.00"))

    def test_future_scheduled_price_resolution(self):
        """Querying at a future scheduled date resolves the upcoming price."""
        future_date = date.today() + timedelta(days=45)
        future_price = Price.get_current_price(self.service, as_of=future_date)
        self.assertIsNotNone(future_price)
        self.assertEqual(future_price.pk, self.p_future.pk)
        self.assertEqual(future_price.amount, Decimal("5000.00"))

    def test_boundary_date_exact_transition(self):
        """Boundary dates resolve strictly to the active interval including endpoints."""
        # Exact last day of expired price: T - 31
        p_t31 = Price.get_current_price(self.service, as_of=date.today() - timedelta(days=31))
        self.assertEqual(p_t31.pk, self.p_expired.pk)

        # Exact first day of current price: T - 30
        p_t30 = Price.get_current_price(self.service, as_of=date.today() - timedelta(days=30))
        self.assertEqual(p_t30.pk, self.p_current.pk)

        # Exact last day of current price: T + 30
        p_t_plus_30 = Price.get_current_price(self.service, as_of=date.today() + timedelta(days=30))
        self.assertEqual(p_t_plus_30.pk, self.p_current.pk)

        # Exact first day of future price: T + 31
        p_t_plus_31 = Price.get_current_price(self.service, as_of=date.today() + timedelta(days=31))
        self.assertEqual(p_t_plus_31.pk, self.p_future.pk)

    def test_overlapping_version_is_rejected(self):
        """Model validation rejects overlapping active price date ranges for the same item and scope."""
        overlapping_p = Price(
            price_type=Price.PriceType.SERVICE,
            content_type=self.srv_ct,
            object_id=self.service.pk,
            scope="standard",
            amount=Decimal("4800.00"),
            currency="INR",
            effective_from=date.today() - timedelta(days=10),
            effective_until=date.today() + timedelta(days=10),
            status=Price.Status.APPROVED,
            is_active=True,
            version=4,
        )
        with self.assertRaises(ValidationError) as ctx:
            overlapping_p.clean()
        self.assertIn("effective_from", ctx.exception.message_dict)

    def test_no_price_exists_returns_none(self):
        """Item with no configured canonical price returns None cleanly."""
        unpriced_service = Service.objects.create(
            code="SRV_UNPRICED",
            name="Unpriced New Service",
        )
        resolved = Price.get_current_price(unpriced_service)
        self.assertIsNone(resolved)
