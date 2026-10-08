from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import AuditEvent, Price, Service, StaffProfile
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
class PriceApprovalAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap_hospital", stdout=None)
        configure_role_permissions()
        cls.today = date(2026, 10, 1)

        # Admin user (has approve_price, change_price, add_price via Administrator group)
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user = User.objects.create_user(
            username="pricing_admin", email="admin@hms.test", password="password", is_staff=True
        )
        cls.admin_user.groups.add(admin_group)
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM-PRICE-01",
        )

        # Second admin user for separation of duties
        cls.approver_user = User.objects.create_user(
            username="pricing_approver", email="approver@hms.test", password="password", is_staff=True
        )
        cls.approver_user.groups.add(admin_group)
        cls.approver_profile = StaffProfile.objects.create(
            user=cls.approver_user,
            employee_id="ADM-PRICE-02",
        )

        # Staff user without approve_price permission (only add/change/view price)
        cls.editor_user = User.objects.create_user(
            username="pricing_editor", email="editor@hms.test", password="password", is_staff=True
        )
        perm_ct = ContentType.objects.get_for_model(Price)
        for codename in ["view_price", "add_price", "change_price"]:
            p = Permission.objects.get(content_type=perm_ct, codename=codename)
            cls.editor_user.user_permissions.add(p)

        cls.editor_profile = StaffProfile.objects.create(
            user=cls.editor_user,
            employee_id="STF-PRICE-01",
        )

        cls.service = Service.objects.create(
            code="SRV-XRAY-CHEST",
            name="Chest X-Ray Single View",
            current_charge=Decimal("500.00"),
            is_active=True,
        )

    def test_unauthorized_user_cannot_approve_or_reject_price(self):
        """User without core.approve_price cannot transition price to APPROVED."""
        self.client.force_login(self.editor_user)
        # Create a draft price
        price = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("600.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.DRAFT,
            is_active=False,
            created_by=self.editor_user,
        )

        change_url = f"/admin/core/price/{price.pk}/change/"
        payload = {
            "price_type": Price.PriceType.SERVICE,
            "content_type": ContentType.objects.get_for_model(Service).pk,
            "object_id": self.service.pk,
            "scope": "standard",
            "version": 1,
            "amount": "600.00",
            "currency": "INR",
            "effective_from": str(self.today),
            "status": Price.Status.APPROVED,
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(change_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)

        price.refresh_from_db()
        self.assertEqual(price.status, Price.Status.DRAFT)
        self.assertFalse(price.is_active)

    def test_separation_of_duties_prevents_creator_from_approving_own_price(self):
        """User who created the price cannot approve their own price even if having approve_price."""
        self.client.force_login(self.admin_user)
        price = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("700.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.PENDING_APPROVAL,
            is_active=False,
            created_by=self.admin_user,
        )

        change_url = f"/admin/core/price/{price.pk}/change/"
        payload = {
            "price_type": Price.PriceType.SERVICE,
            "content_type": ContentType.objects.get_for_model(Service).pk,
            "object_id": self.service.pk,
            "scope": "standard",
            "version": 1,
            "amount": "700.00",
            "currency": "INR",
            "effective_from": str(self.today),
            "status": Price.Status.APPROVED,
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(change_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)

        price.refresh_from_db()
        self.assertEqual(price.status, Price.Status.PENDING_APPROVAL)

    def test_distinct_authorized_approver_can_approve_price_and_audit_event_logged(self):
        """Authorized second approver can approve price, recording approver, timestamp, and AuditEvent."""
        self.client.force_login(self.approver_user)
        price = Price.objects.create(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("750.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.PENDING_APPROVAL,
            is_active=False,
            created_by=self.admin_user,
        )

        change_url = f"/admin/core/price/{price.pk}/change/"
        payload = {
            "price_type": Price.PriceType.SERVICE,
            "content_type": ContentType.objects.get_for_model(Service).pk,
            "object_id": self.service.pk,
            "scope": "standard",
            "version": 1,
            "amount": "750.00",
            "currency": "INR",
            "effective_from": str(self.today),
            "status": Price.Status.APPROVED,
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(change_url, data=payload, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)

        price.refresh_from_db()
        self.assertEqual(price.status, Price.Status.APPROVED)
        self.assertTrue(price.is_active)
        self.assertEqual(price.approved_by, self.approver_user)
        self.assertIsNotNone(price.approved_at)

        # Check AuditEvent
        audit = AuditEvent.objects.filter(
            action="price.approved", target_type="price", target_id=str(price.pk)
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.approver_profile)
        self.assertEqual(audit.details["status"], Price.Status.APPROVED)
        self.assertIn("status", audit.details["changed_fields"])

    def test_unapproved_price_cannot_become_active_validation(self):
        """Price.clean() strictly prevents unapproved prices from being active."""
        from django.core.exceptions import ValidationError
        p = Price(
            price_type=Price.PriceType.SERVICE,
            item=self.service,
            amount=Decimal("800.00"),
            currency="INR",
            effective_from=self.today,
            status=Price.Status.DRAFT,
            is_active=True,
        )
        with self.assertRaises(ValidationError) as ctx:
            p.clean()
        self.assertIn("is_active", ctx.exception.message_dict)
