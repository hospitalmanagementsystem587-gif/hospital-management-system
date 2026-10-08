from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.models import Invoice, InvoiceLine, Patient, Service
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
class ServiceManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_service_user",
            email="admin_service@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Baseline service
        cls.service = Service.objects.create(
            code="CONSULT_OPD",
            name="General OPD Consultation",
            current_charge=Decimal("500.00"),
            is_active=True,
        )

        # Patient for invoice tests
        cls.patient = Patient.objects.create(
            mrn="MRN-SRV-01",
            full_name="Vikas Kumar",
            phone="+919876543210",
        )

    def test_authorized_admin_can_view_service_changelist(self):
        """Admin can view the services changelist with charge and status."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/service/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CONSULT_OPD")
        self.assertContains(response, "General OPD Consultation")

    def test_authorized_admin_can_create_service(self):
        """Admin can create a new service with code, name, and current charge."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/service/add/"
        payload = {
            "code": "ecg_test",  # Uppercase normalization
            "name": "12-Lead Electrocardiogram",
            "current_charge": "350.00",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        srv = Service.objects.filter(code="ECG_TEST").first()
        self.assertIsNotNone(srv)
        self.assertEqual(srv.name, "12-Lead Electrocardiogram")
        self.assertEqual(srv.current_charge, Decimal("350.00"))
        self.assertTrue(srv.is_active)

    def test_duplicate_code_prevented(self):
        """Case-insensitive duplicate service codes are rejected."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/service/add/"
        payload = {
            "code": "consult_opd",  # Duplicate in lowercase
            "name": "Another Consultation",
            "current_charge": "600.00",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("code", form.errors)
        self.assertIn("Service with code 'CONSULT_OPD' already exists.", form.errors["code"])

    def test_negative_charge_rejected(self):
        """Negative service charges are rejected by validation."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/service/add/"
        payload = {
            "code": "XRAY_CHEST",
            "name": "Chest X-Ray",
            "current_charge": "-100.00",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("current_charge", form.errors)

    def test_master_data_edits_do_not_rewrite_historical_invoices(self):
        """Modifying service current_charge or title does not alter historical invoice records."""
        invoice = Invoice.objects.create(
            patient=self.patient,
            number="INV-SRV-101",
            total=Decimal("500.00"),
            status=Invoice.Status.ISSUED,
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            service=self.service,
            description="Historical OPD Consultation Description",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00"),
        )

        # Update service master data
        self.client.force_login(self.admin_user)
        change_url = f"/admin/core/service/{self.service.pk}/change/"
        payload = {
            "code": "CONSULT_OPD",
            "name": "Updated OPD Consultation Title",
            "current_charge": "750.00",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(change_url, data=payload, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)

        # Verify historical line is unaffected
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("500.00"))
        self.assertEqual(line.line_total, Decimal("500.00"))
        self.assertEqual(line.description, "Historical OPD Consultation Description")

    def test_deactivating_service_preserves_historical_invoices(self):
        """Deactivating a service retains all historical invoice lines intact."""
        invoice = Invoice.objects.create(
            patient=self.patient,
            number="INV-SRV-102",
            total=Decimal("500.00"),
            status=Invoice.Status.ISSUED,
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            service=self.service,
            description="OPD Consultation",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00"),
        )
        self.service.is_active = False
        self.service.save(update_fields=["is_active", "updated_at"])

        line.refresh_from_db()
        self.assertEqual(line.service_id, self.service.pk)
        self.assertFalse(self.service.is_active)

    def test_cannot_delete_service_with_invoice_lines(self):
        """Prevent deletion of services referenced by historical invoice lines."""
        invoice = Invoice.objects.create(
            patient=self.patient,
            number="INV-SRV-103",
            total=Decimal("500.00"),
            status=Invoice.Status.ISSUED,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            service=self.service,
            description="Consultation",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00"),
        )
        self.client.force_login(self.admin_user)
        # Attempt delete via admin change view
        del_url = f"/admin/core/service/{self.service.pk}/delete/"
        response = self.client.get(del_url, HTTP_HOST="admin.hms.test")
        # should be 403 because has_delete_permission returns False
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_user_cannot_access_service_admin(self):
        """Non-admin and patient portal users cannot access service admin."""
        patient_user = User.objects.create_user(username="pat_srv", password="PatPassword123!", is_staff=False)
        self.client.force_login(patient_user)
        response = self.client.get("/admin/core/service/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)
