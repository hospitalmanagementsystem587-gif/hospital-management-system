from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    AuditEvent,
    Medicine,
    MedicineBatch,
    StaffProfile,
    StockReceipt,
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
class SupplierWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.doctor_user = User.objects.create_user("doctor_sup", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user, employee_id="DOC-SUP-1"
        )

        cls.reception_user = User.objects.create_user("rec_sup", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user, employee_id="REC-SUP-1"
        )

        cls.pharmacy_user = User.objects.create_user("pharm_sup", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user, employee_id="PHM-SUP-1"
        )

        cls.admin_user = User.objects.create_user(
            "admin_sup", password="password", is_staff=True
        )
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user, employee_id="ADM-SUP-1"
        )

        cls.ordinary_user = User.objects.create_user("ord_sup", password="password")

        cls.sup_active = Supplier.objects.create(
            code="SUP-ALPHA",
            name="Alpha Pharma Corp",
            phone="+91 9999988888",
            email="alpha@pharma.test",
            address="123 Alpha Industrial Area",
            is_active=True,
        )

        cls.sup_inactive = Supplier.objects.create(
            code="SUP-BETA",
            name="Beta Distributors",
            phone="+91 8888877777",
            email="beta@distrib.test",
            address="456 Beta Logistics Park",
            is_active=False,
        )

    def test_anonymous_access_redirects(self):
        res = self.client.get("/store/suppliers/", HTTP_HOST="store.hms.test")
        self.assertRedirects(res, "/accounts/login/?next=/store/suppliers/")

        res_create = self.client.get("/store/suppliers/create/", HTTP_HOST="store.hms.test")
        self.assertRedirects(res_create, "/accounts/login/?next=/store/suppliers/create/")

        res_edit = self.client.get(
            f"/store/suppliers/{self.sup_active.pk}/edit/", HTTP_HOST="store.hms.test"
        )
        self.assertRedirects(
            res_edit, f"/accounts/login/?next=/store/suppliers/{self.sup_active.pk}/edit/"
        )

    def test_unauthorized_roles_forbidden(self):
        for user in [self.doctor_user, self.reception_user, self.ordinary_user]:
            self.client.force_login(user)
            res = self.client.get("/store/suppliers/", HTTP_HOST="store.hms.test")
            self.assertEqual(res.status_code, 403, f"User {user.username} should get 403")

            res_create = self.client.get("/store/suppliers/create/", HTTP_HOST="store.hms.test")
            self.assertEqual(res_create.status_code, 403)

            res_edit = self.client.get(
                f"/store/suppliers/{self.sup_active.pk}/edit/", HTTP_HOST="store.hms.test"
            )
            self.assertEqual(res_edit.status_code, 403)

    def test_pharmacy_role_access(self):
        self.client.force_login(self.pharmacy_user)
        res = self.client.get("/store/suppliers/", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Supplier Directory")
        self.assertContains(res, "Alpha Pharma Corp")

        res_create = self.client.get("/store/suppliers/create/", HTTP_HOST="store.hms.test")
        self.assertEqual(res_create.status_code, 200)
        self.assertContains(res_create, "Add New Supplier")

        res_edit = self.client.get(
            f"/store/suppliers/{self.sup_active.pk}/edit/", HTTP_HOST="store.hms.test"
        )
        self.assertEqual(res_edit.status_code, 200)
        self.assertContains(res_edit, "Edit Supplier")

    def test_administrator_role_access(self):
        self.client.force_login(self.admin_user)
        res = self.client.get("/store/suppliers/", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Supplier Directory")

        res_create = self.client.get("/store/suppliers/create/", HTTP_HOST="store.hms.test")
        self.assertEqual(res_create.status_code, 200)

        res_edit = self.client.get(
            f"/store/suppliers/{self.sup_active.pk}/edit/", HTTP_HOST="store.hms.test"
        )
        self.assertEqual(res_edit.status_code, 200)

    def test_supplier_filtering_and_search(self):
        self.client.force_login(self.pharmacy_user)

        # Search by name
        res = self.client.get("/store/suppliers/?q=Alpha", HTTP_HOST="store.hms.test")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SUP-ALPHA")
        self.assertNotContains(res, "SUP-BETA")

        # Search by code
        res_code = self.client.get("/store/suppliers/?q=SUP-BETA", HTTP_HOST="store.hms.test")
        self.assertEqual(res_code.status_code, 200)
        self.assertContains(res_code, "Beta Distributors")
        self.assertNotContains(res_code, "Alpha Pharma Corp")

        # Filter active only
        res_act = self.client.get("/store/suppliers/?status=active", HTTP_HOST="store.hms.test")
        self.assertEqual(res_act.status_code, 200)
        self.assertContains(res_act, "Alpha Pharma Corp")
        self.assertNotContains(res_act, "Beta Distributors")

        # Filter inactive only
        res_inact = self.client.get(
            "/store/suppliers/?status=inactive", HTTP_HOST="store.hms.test"
        )
        self.assertEqual(res_inact.status_code, 200)
        self.assertContains(res_inact, "Beta Distributors")
        self.assertNotContains(res_inact, "Alpha Pharma Corp")

    def test_supplier_create_workflow(self):
        self.client.force_login(self.pharmacy_user)
        payload = {
            "code": "SUP-GAMMA",
            "name": "Gamma Lifesciences",
            "phone": "+91 9777766666",
            "email": "gamma@lifesciences.test",
            "address": "789 Gamma Road",
            "is_active": True,
        }
        res = self.client.post(
            "/store/suppliers/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res, "/store/suppliers/")

        supplier = Supplier.objects.get(code="SUP-GAMMA")
        self.assertEqual(supplier.name, "Gamma Lifesciences")
        self.assertTrue(supplier.is_active)

        # Audit event created
        audit = AuditEvent.objects.filter(
            target_type="supplier", target_id=str(supplier.pk), action="pharmacy.supplier_created"
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details["code"], "SUP-GAMMA")

    def test_duplicate_supplier_code_rejected(self):
        self.client.force_login(self.pharmacy_user)
        payload = {
            "code": "SUP-ALPHA",  # Duplicate code
            "name": "Duplicate Alpha Vendor",
            "phone": "",
            "email": "",
            "address": "",
            "is_active": True,
        }
        res = self.client.post(
            "/store/suppliers/create/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFormError(
            res.context["form"], "code", "A supplier with this code already exists."
        )

    def test_supplier_update_and_continuity(self):
        self.client.force_login(self.pharmacy_user)

        # Create medicine, receipt and batch linked to sup_active
        med = Medicine.objects.create(
            code="MED-HIST-SUP",
            generic_name="Hist Med",
            unit="tablet",
            is_active=True,
        )
        receipt = StockReceipt.objects.create(
            number="REC-SUP-HIST-01",
            supplier=self.sup_active,
            received_at=timezone.now(),
        )
        batch = MedicineBatch.objects.create(
            medicine=med,
            receipt=receipt,
            batch_number="BAT-SUP-HIST",
            expiry_date=timezone.localdate(),
            purchase_price=Decimal("10.00"),
            sale_price=Decimal("15.00"),
            quantity_received=Decimal("100"),
            quantity_on_hand=Decimal("100"),
        )

        # Deactivate supplier
        payload = {
            "code": self.sup_active.code,
            "name": "Alpha Pharma Corp (Deactivated)",
            "phone": self.sup_active.phone,
            "email": self.sup_active.email,
            "address": self.sup_active.address,
            "is_active": False,
        }
        res = self.client.post(
            f"/store/suppliers/{self.sup_active.pk}/edit/",
            payload,
            HTTP_HOST="store.hms.test",
        )
        self.assertRedirects(res, "/store/suppliers/")

        self.sup_active.refresh_from_db()
        self.assertFalse(self.sup_active.is_active)
        self.assertEqual(self.sup_active.name, "Alpha Pharma Corp (Deactivated)")

        # Historical references remain intact
        receipt.refresh_from_db()
        self.assertEqual(receipt.supplier, self.sup_active)
        batch.refresh_from_db()
        self.assertEqual(batch.receipt.supplier, self.sup_active)

        # Audit event created
        audit = AuditEvent.objects.filter(
            target_type="supplier",
            target_id=str(self.sup_active.pk),
            action="pharmacy.supplier_updated",
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("is_active", audit.details["changed_fields"])
        self.assertIn("name", audit.details["changed_fields"])
