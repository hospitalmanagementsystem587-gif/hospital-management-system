from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from core.forms import PriceForm
from core.models import Price, Service, StaffProfile, Ward
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
class CanonicalPricingArchitectureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_price_user",
            email="admin_price@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Non-admin user (Reception)
        cls.reception_user = User.objects.create_user(
            username="reception_price_user",
            email="reception_price@test.hms",
            password="ReceptionPassword123!",
            is_staff=True,
        )
        reception_group = Group.objects.get(name="Reception")
        cls.reception_user.groups.add(reception_group)

        # Doctor profile
        cls.doctor_user = User.objects.create_user(
            username="doctor_price_user",
            email="doc_price@test.hms",
            password="DocPassword123!",
            is_staff=True,
        )
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-PRC-01",
            consultation_fee=600,
        )

        # Clinical service
        cls.service = Service.objects.create(
            code="SRV_PHYSIO",
            name="Physical Therapy Session",
            current_charge=Decimal("750.00"),
        )

        # Ward
        cls.ward = Ward.objects.create(
            code="WARD_DELUXE",
            name="Deluxe Private Wing",
            category=Ward.Category.PRIVATE,
            daily_rate=Decimal("3500.00"),
        )

        # Baseline canonical price for service
        cls.srv_ct = ContentType.objects.get_for_model(cls.service)
        cls.canonical_srv_price = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            content_type=cls.srv_ct,
            object_id=cls.service.pk,
            scope="standard",
            amount=Decimal("750.00"),
            currency="INR",
            effective_from=date.today() - timedelta(days=10),
            status=Price.Status.APPROVED,
            is_active=True,
        )

    def test_authorized_admin_can_view_price_changelist(self):
        """Admin can access Price changelist in admin portal."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/price/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SRV_PHYSIO")
        self.assertContains(response, "750.00")

    def test_unauthorized_staff_cannot_access_price_cms(self):
        """Reception staff without price management permissions cannot access Price admin."""
        self.client.force_login(self.reception_user)
        response = self.client.get("/admin/core/price/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_submit_canonical_price_for_approval(self):
        """A creator can submit a consultation price but cannot self-approve it."""
        self.client.force_login(self.admin_user)
        doc_ct = ContentType.objects.get_for_model(self.doctor_profile)
        post_data = {
            "price_type": Price.PriceType.CONSULTATION,
            "content_type": doc_ct.pk,
            "object_id": self.doctor_profile.pk,
            "scope": "initial",
            "amount": "850.00",
            "currency": "INR",
            "effective_from": date.today().isoformat(),
            "status": Price.Status.PENDING_APPROVAL,
            "version": 1,
            "notes": "Revised standard specialist OPD fee.",
        }
        response = self.client.post(
            "/admin/core/price/add/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        created = Price.objects.get(
            content_type=doc_ct,
            object_id=self.doctor_profile.pk,
            scope="initial",
        )
        self.assertEqual(created.amount, Decimal("850.00"))
        self.assertEqual(created.currency, "INR")
        self.assertFalse(created.is_active)
        self.assertEqual(created.created_by, self.admin_user)
        self.assertIsNone(created.approved_by)

    def test_get_current_price_resolves_approved_active_price(self):
        """get_current_price classmethod accurately resolves the active canonical price."""
        resolved = Price.get_current_price(self.service, scope="standard")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.amount, Decimal("750.00"))
        self.assertEqual(resolved.pk, self.canonical_srv_price.pk)

    def test_get_current_price_excludes_unapproved_or_inactive_records(self):
        """get_current_price ignores draft, pending, or inactive prices."""
        draft_price = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            content_type=self.srv_ct,
            object_id=self.service.pk,
            scope="special_promo",
            amount=Decimal("500.00"),
            currency="INR",
            effective_from=date.today(),
            status=Price.Status.DRAFT,
            is_active=False,
        )
        resolved = Price.get_current_price(self.service, scope="special_promo")
        self.assertIsNone(resolved)

        draft_price.status = Price.Status.APPROVED
        draft_price.is_active = False
        draft_price.save()
        resolved2 = Price.get_current_price(self.service, scope="special_promo")
        self.assertIsNone(resolved2)

    def test_price_form_rejects_negative_amount(self):
        """PriceForm rejects negative amounts."""
        form = PriceForm(data={
            "price_type": Price.PriceType.CUSTOM,
            "amount": "-50.00",
            "currency": "INR",
            "effective_from": date.today(),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test_price_form_rejects_invalid_date_range(self):
        """PriceForm rejects effective_until earlier than effective_from."""
        form = PriceForm(data={
            "price_type": Price.PriceType.CUSTOM,
            "amount": "100.00",
            "currency": "INR",
            "effective_from": date.today(),
            "effective_until": date.today() - timedelta(days=1),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("effective_until", form.errors)

    def test_price_form_rejects_mismatched_target_type(self):
        """A service price cannot point at an unrelated doctor profile."""
        form = PriceForm(data={
            "price_type": Price.PriceType.SERVICE,
            "content_type": ContentType.objects.get_for_model(self.doctor_profile).pk,
            "object_id": self.doctor_profile.pk,
            "scope": "standard",
            "amount": "100.00",
            "currency": "INR",
            "effective_from": date.today(),
            "status": Price.Status.DRAFT,
            "version": 1,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("content_type", form.errors)

    def test_price_form_normalizes_currency_and_scope(self):
        form = PriceForm(data={
            "price_type": Price.PriceType.SERVICE,
            "content_type": self.srv_ct.pk,
            "object_id": self.service.pk,
            "scope": " Standard ",
            "amount": "100.00",
            "currency": "inr",
            "effective_from": date.today() + timedelta(days=100),
            "status": Price.Status.DRAFT,
            "version": 2,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.currency, "INR")
        self.assertEqual(form.instance.scope, "standard")
