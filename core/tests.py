from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import re
from threading import Barrier
from unittest import skipUnless

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.db.models import Sum
from django.core.management import call_command
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Appointment,
    Adjustment,
    AuditEvent,
    Consultation,
    Department,
    HospitalSettings,
    DispensingLine,
    Invoice,
    InvoiceLine,
    Medicine,
    MedicineBatch,
    NumberSequence,
    Patient,
    Payment,
    PaymentMethod,
    PharmacyReturn,
    PharmacySale,
    PharmacySaleLine,
    Prescription,
    PrescriptionItem,
    Refund,
    Service,
    StaffProfile,
    Dispensing,
    StockMovement,
    StockReceipt,
    Supplier,
    VisitType,
    ReturnLine,
)
from .authorization import doctor_patient_queryset
from .forms import AppointmentForm, PatientForm
from .services.numbering import next_number


class PublicPagesTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hospital Management System")

    def test_home_page_uses_configured_hospital_name(self):
        HospitalSettings.objects.create(name="Synthetic Community Hospital")

        response = self.client.get("/")

        self.assertContains(response, "Synthetic Community Hospital")

    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class AuthenticationLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff-test",
            email="staff@example.test",
            password="Synthetic-Password-123!",
        )

    def test_active_staff_can_log_in_and_log_out(self):
        response = self.client.post(
            reverse("login"),
            {"username": "staff-test", "password": "Synthetic-Password-123!"},
        )

        self.assertRedirects(response, "/")
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_invalid_and_inactive_users_cannot_log_in(self):
        invalid_response = self.client.post(
            reverse("login"), {"username": "staff-test", "password": "wrong"}
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "Please enter a correct")

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        inactive_response = self.client.post(
            reverse("login"),
            {"username": "staff-test", "password": "Synthetic-Password-123!"},
        )
        self.assertEqual(inactive_response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_repeated_failed_logins_are_throttled(self):
        from django.core.cache import cache

        cache.clear()
        for _ in range(5):
            response = self.client.post(
                reverse("login"),
                {"username": "staff-test", "password": "wrong-password"},
            )
            if _ < 4:
                self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("login"),
            {"username": "staff-test", "password": "wrong-password"},
        )
        self.assertContains(
            response,
            "Too many failed login attempts",
            status_code=429,
        )

    def test_deactivated_user_session_loses_protected_access(self):
        self.client.force_login(self.user)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_password_change_requires_login_and_updates_password(self):
        response = self.client.get(reverse("password_change"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "Synthetic-Password-123!",
                "new_password1": "New-Synthetic-Password-456!",
                "new_password2": "New-Synthetic-Password-456!",
            },
        )

        self.assertRedirects(response, reverse("password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-Synthetic-Password-456!"))

    def test_password_reset_sends_email_without_exposing_user_existence(self):
        response = self.client.post(
            reverse("password_reset"), {"email": self.user.email}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

        reset_path = re.search(
            r"http://testserver(/accounts/reset/[^\s]+)", mail.outbox[0].body
        ).group(1)
        response = self.client.get(reset_path, follow=True)
        self.assertEqual(response.status_code, 200)
        confirm_path = response.request["PATH_INFO"]
        response = self.client.post(
            confirm_path,
            {
                "new_password1": "Reset-Synthetic-Password-789!",
                "new_password2": "Reset-Synthetic-Password-789!",
            },
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Reset-Synthetic-Password-789!"))

        response = self.client.post(
            reverse("password_reset"), {"email": "unknown@example.test"}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_staff_cannot_self_register_or_open_admin(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get("/accounts/signup/").status_code, 404)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_bootstrapped_superuser_can_manage_staff_profiles(self):
        administrator = get_user_model().objects.create_superuser(
            username="admin-test",
            email="admin@example.test",
            password="Synthetic-Admin-Password-123!",
        )
        self.client.force_login(administrator)

        response = self.client.get(reverse("admin:core_staffprofile_changelist"))

        self.assertEqual(response.status_code, 200)


class SchemaConstraintTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            mrn="TEST-001", full_name="Synthetic Patient"
        )

    def test_patient_mrn_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Patient.objects.create(mrn="TEST-001", full_name="Duplicate")

    def test_hospital_settings_has_a_singleton_key(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            HospitalSettings.objects.create(id=2, name="Second Hospital")

    def test_invoice_line_rejects_negative_money(self):
        invoice = Invoice.objects.create(number="INV-TEST-001", patient=self.patient)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InvoiceLine.objects.create(
                invoice=invoice,
                description="Invalid synthetic line",
                quantity=Decimal("1"),
                unit_price=Decimal("-1.00"),
                line_total=Decimal("-1.00"),
            )

    def test_invoice_rejects_unknown_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Invoice.objects.create(
                number="INV-TEST-INVALID",
                patient=self.patient,
                status="unknown",
            )

    def test_batch_rejects_negative_stock(self):
        supplier = Supplier.objects.create(code="SUP-TEST", name="Synthetic Supplier")
        receipt = StockReceipt.objects.create(
            number="REC-TEST-001",
            supplier=supplier,
            received_at="2026-01-01T00:00:00Z",
        )
        medicine = Medicine.objects.create(
            code="MED-TEST", generic_name="Synthetic Medicine", unit="tablet"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            MedicineBatch.objects.create(
                medicine=medicine,
                receipt=receipt,
                batch_number="BATCH-TEST",
                expiry_date="2027-01-01",
                purchase_price=Decimal("1.00"),
                sale_price=Decimal("2.00"),
                quantity_received=Decimal("10"),
                quantity_on_hand=Decimal("-1"),
            )

    def test_stock_movement_must_balance(self):
        supplier = Supplier.objects.create(code="SUP-TEST", name="Synthetic Supplier")
        receipt = StockReceipt.objects.create(
            number="REC-TEST-001",
            supplier=supplier,
            received_at="2026-01-01T00:00:00Z",
        )
        medicine = Medicine.objects.create(
            code="MED-TEST", generic_name="Synthetic Medicine", unit="tablet"
        )
        batch = MedicineBatch.objects.create(
            medicine=medicine,
            receipt=receipt,
            batch_number="BATCH-TEST",
            expiry_date="2027-01-01",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("10"),
            quantity_on_hand=Decimal("10"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(
                batch=batch,
                kind=StockMovement.Kind.DISPENSE,
                quantity_delta=Decimal("-2"),
                quantity_before=Decimal("10"),
                quantity_after=Decimal("9"),
            )


class HospitalBootstrapTests(TestCase):
    def test_bootstrap_is_idempotent_and_creates_roles_and_sequences(self):
        call_command("bootstrap_hospital", stdout=None)
        call_command("bootstrap_hospital", stdout=None)

        self.assertEqual(HospitalSettings.objects.count(), 1)
        self.assertEqual(
            set(Group.objects.values_list("name", flat=True)),
            {"Reception", "Pharmacy", "Doctor", "Administrator"},
        )
        self.assertEqual(NumberSequence.objects.count(), 8)

    def test_numbering_allocates_distinct_values_from_config(self):
        NumberSequence.objects.create(code="PATIENT", prefix="P-")

        self.assertEqual(next_number("PATIENT"), "P-1")
        self.assertEqual(next_number("PATIENT"), "P-2")
        self.assertEqual(NumberSequence.objects.get(code="PATIENT").next_value, 3)

    def test_configuration_admin_requires_model_permission(self):
        staff = get_user_model().objects.create_user(
            username="config-staff",
            password="Synthetic-Password-123!",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("admin:core_service_changelist"))

        self.assertEqual(response.status_code, 403)

    def test_service_price_change_does_not_rewrite_invoice_snapshot(self):
        service = Service.objects.create(
            code="CONSULT",
            name="Consultation",
            current_charge=Decimal("500.00"),
        )
        patient = Patient.objects.create(
            mrn="SNAPSHOT-001", full_name="Synthetic Patient"
        )
        invoice = Invoice.objects.create(number="SNAPSHOT-INV", patient=patient)
        line = InvoiceLine.objects.create(
            invoice=invoice,
            service=service,
            description="Consultation",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            tax_rate=None,
            discount_amount=Decimal("0.00"),
            line_total=Decimal("500.00"),
        )

        service.current_charge = Decimal("700.00")
        service.save(update_fields=("current_charge", "updated_at"))
        line.refresh_from_db()

        self.assertEqual(line.unit_price, Decimal("500.00"))
        self.assertIsNone(line.tax_rate)

    def test_admin_master_data_change_is_logged(self):
        administrator = get_user_model().objects.create_superuser(
            username="master-admin",
            email="master-admin@example.test",
            password="Synthetic-Admin-Password-123!",
        )
        self.client.force_login(administrator)

        response = self.client.post(
            reverse("admin:core_service_add"),
            {
                "code": "SVC-TEST",
                "name": "Synthetic Service",
                "current_charge": "",
                "is_active": "on",
                "_save": "Save",
            },
        )

        service = Service.objects.get(code="SVC-TEST")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LogEntry.objects.filter(
                user=administrator,
                content_type__model="service",
                object_id=str(service.pk),
                action_flag=ADDITION,
            ).exists()
        )


class BillingWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.reception = get_user_model().objects.create_user(
            username="billing-reception",
            password="Synthetic-Password-123!",
        )
        self.reception.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(
            user=self.reception,
            employee_id="BILL-RECEPTION-001",
        )
        self.patient = Patient.objects.create(
            mrn="BILL-001",
            full_name="Billing Patient",
            phone="5550200",
        )
        self.service = Service.objects.create(
            code="CONSULT-BILL",
            name="Consultation Billable",
            current_charge=Decimal("500.00"),
        )
        self.method = PaymentMethod.objects.create(
            code="CASH",
            name="Cash",
        )

    def test_reception_can_create_invoice_and_record_payment(self):
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("invoice_create"),
            {
                "patient": self.patient.pk,
                "service": self.service.pk,
                "quantity": "1",
                "unit_price": "500.00",
                "description": "Consultation",
                "request_key": "00000000-0000-0000-0000-000000000016",
            },
        )

        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get(patient=self.patient)
        self.assertEqual(invoice.number, "1")
        self.assertEqual(invoice.total, Decimal("500.00"))
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        duplicate_invoice = self.client.post(
            reverse("invoice_create"),
            {
                "patient": self.patient.pk,
                "service": self.service.pk,
                "quantity": "1",
                "unit_price": "500.00",
                "description": "Consultation",
                "request_key": "00000000-0000-0000-0000-000000000016",
            },
        )
        self.assertEqual(duplicate_invoice.status_code, 302)
        self.assertEqual(Invoice.objects.filter(patient=self.patient).count(), 1)

        response = self.client.post(
            reverse("payment_create", args=[invoice.pk]),
            {
                "method": self.method.pk,
                "amount": "500.00",
                "reference": "CASH-001",
                "request_key": "00000000-0000-0000-0000-000000000014",
            },
        )

        self.assertEqual(response.status_code, 302)
        payment = invoice.payments.get()
        self.assertEqual(payment.amount, Decimal("500.00"))
        self.assertEqual(payment.reference, "CASH-001")

    def test_payment_cannot_exceed_invoice_balance(self):
        invoice = Invoice.objects.create(
            number="OVERPAY-001",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("500.00"),
        )
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("payment_create", args=[invoice.pk]),
            {
                "method": self.method.pk,
                "amount": "500.01",
                "request_key": "00000000-0000-0000-0000-000000000015",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(invoice.payments.exists())

    def test_duplicate_payment_submission_creates_one_receipt(self):
        invoice = Invoice.objects.create(
            number="DUPLICATE-PAYMENT-001",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("500.00"),
        )
        self.client.force_login(self.reception)
        payload = {
            "method": self.method.pk,
            "amount": "100.00",
            "reference": "DUPLICATE-SYNTHETIC",
            "request_key": "00000000-0000-0000-0000-000000000013",
        }
        url = reverse("payment_create", args=[invoice.pk])

        first = self.client.post(url, payload)
        duplicate = self.client.post(url, payload)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(duplicate.status_code, 302)
        self.assertEqual(invoice.payments.count(), 1)

    def _create_administrator(self):
        user = get_user_model().objects.create_user(
            username="billing-administrator",
            password="Synthetic-Password-123!",
        )
        user.groups.add(Group.objects.get(name="Administrator"))
        profile = StaffProfile.objects.create(
            user=user,
            employee_id="BILL-ADMIN-001",
        )
        return user, profile

    def test_admin_discount_is_reasoned_audited_and_tax_defaults_to_zero(self):
        administrator, _ = self._create_administrator()
        self.client.force_login(administrator)

        response = self.client.post(
            reverse("invoice_create"),
            {
                "patient": self.patient.pk,
                "service": self.service.pk,
                "quantity": "1",
                "unit_price": "500.00",
                "discount_amount": "25.00",
                "reason": "Approved synthetic discount",
                "request_key": "00000000-0000-0000-0000-000000000017",
            },
        )

        invoice = Invoice.objects.get(patient=self.patient)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invoice.total, Decimal("475.00"))
        self.assertEqual(invoice.tax_total, Decimal("0.00"))
        self.assertEqual(invoice.lines.get().discount_amount, Decimal("25.00"))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="financial.discount_applied",
                target_id=str(invoice.pk),
                details__reason="Approved synthetic discount",
            ).exists()
        )

    def test_adjustment_and_refund_are_audited_and_change_balance(self):
        administrator, profile = self._create_administrator()
        invoice = Invoice.objects.create(
            number="CONTROLLED-001",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("500.00"),
        )
        payment = Payment.objects.create(
            receipt_number="CONTROLLED-REC-001",
            invoice=invoice,
            method=self.method,
            amount=Decimal("500.00"),
            received_at=timezone.now(),
        )
        self.client.force_login(administrator)

        response = self.client.post(
            reverse("invoice_refund", args=[invoice.pk]),
            {
                "payment": payment.pk,
                "amount": "50.00",
                "reason": "Synthetic refund",
                "request_key": "00000000-0000-0000-0000-000000000018",
            },
        )
        self.assertEqual(response.status_code, 302)
        refund = Refund.objects.get(payment=payment)
        self.assertEqual(refund.status, Refund.Status.ISSUED)
        self.assertEqual(refund.approved_by, profile)
        self.assertEqual(
            AuditEvent.objects.filter(action="financial.refund_issued").count(), 1
        )
        duplicate_refund = self.client.post(
            reverse("invoice_refund", args=[invoice.pk]),
            {
                "payment": payment.pk,
                "amount": "50.00",
                "reason": "Synthetic refund",
                "request_key": "00000000-0000-0000-0000-000000000018",
            },
        )
        self.assertEqual(duplicate_refund.status_code, 302)
        self.assertEqual(Refund.objects.filter(payment=payment).count(), 1)

        response = self.client.post(
            reverse("invoice_adjustment", args=[invoice.pk]),
            {
                "kind": "adjustment",
                "amount": "20.00",
                "reason": "Synthetic correction",
                "request_key": "00000000-0000-0000-0000-000000000019",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Adjustment.objects.get(invoice=invoice).amount, Decimal("20.00")
        )
        self.assertEqual(
            AuditEvent.objects.filter(action="financial.adjustment_created").count(), 1
        )
        duplicate_adjustment = self.client.post(
            reverse("invoice_adjustment", args=[invoice.pk]),
            {
                "kind": "adjustment",
                "amount": "20.00",
                "reason": "Synthetic correction",
                "request_key": "00000000-0000-0000-0000-000000000019",
            },
        )
        self.assertEqual(duplicate_adjustment.status_code, 302)
        self.assertEqual(Adjustment.objects.filter(invoice=invoice).count(), 1)
        self.assertEqual(
            invoice.payments.get().refunds.get().reason, "Synthetic refund"
        )

    def test_reception_cannot_discount_or_void_invoice(self):
        self.client.force_login(self.reception)
        response = self.client.post(
            reverse("invoice_create"),
            {
                "patient": self.patient.pk,
                "service": self.service.pk,
                "quantity": "1",
                "unit_price": "500.00",
                "discount_amount": "10.00",
                "reason": "Unauthorized discount",
                "request_key": "00000000-0000-0000-0000-000000000020",
            },
        )
        self.assertEqual(response.status_code, 403)

        invoice = Invoice.objects.create(
            number="RECEPTION-FINANCE-DENIAL",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("10.00"),
        )
        for route in ("invoice_adjustment", "invoice_refund"):
            with self.subTest(route=route):
                response = self.client.post(
                    reverse(route, args=[invoice.pk]),
                    {"amount": "1.00", "reason": "Unauthorized"},
                )
                self.assertEqual(response.status_code, 403)

        void_invoice = Invoice.objects.create(
            number="NO-RECEPTION-VOID",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("10.00"),
        )
        response = self.client.post(
            reverse("invoice_void", args=[void_invoice.pk]),
            {"reason": "Unauthorized void"},
        )
        self.assertEqual(response.status_code, 403)
        void_invoice.refresh_from_db()
        self.assertEqual(void_invoice.status, Invoice.Status.ISSUED)

    def test_doctor_and_pharmacy_cannot_access_financial_urls(self):
        invoice = Invoice.objects.create(
            number="ROLE-FINANCE-DENIAL",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("10.00"),
        )
        for role in ("Doctor", "Pharmacy"):
            user = get_user_model().objects.create_user(
                username=f"{role.lower()}-finance-denial",
                password="Synthetic-Password-123!",
            )
            user.groups.add(Group.objects.get(name=role))
            StaffProfile.objects.create(
                user=user,
                employee_id=f"{role.upper()}-FINANCE-DENIAL",
            )
            self.client.force_login(user)
            with self.subTest(role=role):
                for route in ("invoice_list", "invoice_detail"):
                    args = [invoice.pk] if route == "invoice_detail" else []
                    self.assertEqual(
                        self.client.get(reverse(route, args=args)).status_code, 403
                    )
                for route in ("payment_create", "invoice_refund", "invoice_adjustment"):
                    self.assertEqual(
                        self.client.post(
                            reverse(route, args=[invoice.pk]),
                            {"amount": "1.00", "reason": "Unauthorized"},
                        ).status_code,
                        403,
                    )

    def test_invoice_detail_renders_reception_payment_controls(self):
        invoice = Invoice.objects.create(
            number="DETAIL-001",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("100.00"),
        )
        self.client.force_login(self.reception)

        response = self.client.get(reverse("invoice_detail", args=[invoice.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Record payment")
        self.assertContains(response, "100.00")

    def test_admin_can_void_unsettled_invoice_with_reason(self):
        administrator, _ = self._create_administrator()
        invoice = Invoice.objects.create(
            number="VOID-001",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("10.00"),
        )
        self.client.force_login(administrator)

        response = self.client.post(
            reverse("invoice_void", args=[invoice.pk]),
            {"reason": "Duplicate synthetic invoice"},
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invoice.status, Invoice.Status.VOIDED)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="financial.invoice_voided",
                target_id=str(invoice.pk),
                details__reason="Duplicate synthetic invoice",
            ).exists()
        )


@skipUnless(
    connection.features.has_select_for_update,
    "Concurrent row-lock tests require a database supporting SELECT FOR UPDATE.",
)
class ConcurrencyIntegrityTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.pharmacy = get_user_model().objects.create_user(
            username="concurrency-pharmacy",
            password="Synthetic-Password-123!",
        )
        self.pharmacy.groups.add(Group.objects.get(name="Pharmacy"))
        StaffProfile.objects.create(user=self.pharmacy, employee_id="CONC-PHARM-001")
        self.patient = Patient.objects.create(
            mrn="CONC-001", full_name="Concurrency Synthetic Patient"
        )

    def post_concurrently(self, user, url, payloads):
        barrier = Barrier(len(payloads))

        def post(payload):
            close_old_connections()
            try:
                client = Client()
                client.force_login(user)
                barrier.wait(timeout=10)
                return client.post(url, payload).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            return list(pool.map(post, payloads))

    def test_concurrent_otc_sales_cannot_oversell_stock(self):
        medicine = Medicine.objects.create(
            code="CONC-MED-001",
            generic_name="Concurrency Medicine",
            unit="tablet",
            is_otc=True,
        )
        supplier = Supplier.objects.create(code="CONC-SUP-001", name="Supplier")
        receipt = StockReceipt.objects.create(
            number="CONC-RECEIPT-001", supplier=supplier, received_at=timezone.now()
        )
        batch = MedicineBatch.objects.create(
            medicine=medicine,
            receipt=receipt,
            batch_number="CONC-BATCH-001",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("5"),
            quantity_on_hand=Decimal("5"),
        )
        payloads = [
            {
                "batch": batch.pk,
                "quantity": "4",
                "request_key": f"00000000-0000-0000-0000-0000000000{value}",
            }
            for value in ("22", "23")
        ]

        statuses = self.post_concurrently(
            self.pharmacy, reverse("pharmacy_sale_create"), payloads
        )

        self.assertEqual(sorted(statuses), [302, 400])
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("1"))
        self.assertEqual(PharmacySale.objects.count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(kind=StockMovement.Kind.SALE).count(), 1
        )

    def test_concurrent_payments_cannot_exceed_invoice_balance(self):
        reception = get_user_model().objects.create_user(
            username="concurrency-reception",
            password="Synthetic-Password-123!",
        )
        reception.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(user=reception, employee_id="CONC-RECEPTION-001")
        method = PaymentMethod.objects.create(code="CONC-CASH", name="Cash")
        invoice = Invoice.objects.create(
            number="CONC-INVOICE-001",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            total=Decimal("100.00"),
        )
        payloads = [
            {
                "method": method.pk,
                "amount": "60.00",
                "request_key": f"00000000-0000-0000-0000-0000000000{value}",
            }
            for value in ("24", "25")
        ]

        statuses = self.post_concurrently(
            reception, reverse("payment_create", args=[invoice.pk]), payloads
        )

        self.assertEqual(sorted(statuses), [302, 400])
        self.assertEqual(invoice.payments.count(), 1)
        self.assertEqual(
            invoice.payments.get().amount,
            Decimal("60.00"),
        )


class PharmacyWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.pharmacy = get_user_model().objects.create_user(
            username="pharmacy-staff",
            password="Synthetic-Password-123!",
        )
        self.pharmacy.groups.add(Group.objects.get(name="Pharmacy"))
        self.pharmacy_profile = StaffProfile.objects.create(
            user=self.pharmacy,
            employee_id="PHARM-001",
        )
        self.supplier = Supplier.objects.create(
            code="SUP-001",
            name="Synthetic Supplier",
        )
        self.medicine = Medicine.objects.create(
            code="MED-001",
            generic_name="Synthetic Medicine",
            unit="tablet",
        )
        self.patient = Patient.objects.create(
            mrn="PHARM-001",
            full_name="Pharmacy Patient",
        )
        self.doctor_user = get_user_model().objects.create_user(
            username="pharmacy-doctor",
            password="Synthetic-Password-123!",
        )
        self.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        self.doctor = StaffProfile.objects.create(
            user=self.doctor_user,
            employee_id="DOC-100",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            clinical_notes="Synthetic clinical note",
            diagnosis="Synthetic diagnosis",
        )
        self.prescription = Prescription.objects.create(
            number="RX-001",
            consultation=self.consultation,
            patient=self.patient,
            doctor=self.doctor,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )
        self.item = PrescriptionItem.objects.create(
            prescription=self.prescription,
            medicine=self.medicine,
            dosage="500mg",
            frequency="BD",
            duration="5 days",
            instructions="After food",
            quantity=Decimal("10"),
        )

    def test_pharmacy_can_receive_stock_and_dispense_prescription(self):
        self.client.force_login(self.pharmacy)

        response = self.client.post(
            reverse("stock_receipt_create"),
            {
                "supplier": self.supplier.pk,
                "medicine": self.medicine.pk,
                "request_key": "00000000-0000-0000-0000-000000000001",
                "batch_number": "BATCH-001",
                "expiry_date": "2028-12-31",
                "purchase_price": "1.00",
                "sale_price": "2.00",
                "quantity_received": "10",
            },
        )

        self.assertEqual(response.status_code, 302)
        batch = MedicineBatch.objects.get(batch_number="BATCH-001")
        self.assertEqual(batch.quantity_on_hand, Decimal("10"))
        duplicate_receipt = self.client.post(
            reverse("stock_receipt_create"),
            {
                "supplier": self.supplier.pk,
                "medicine": self.medicine.pk,
                "request_key": "00000000-0000-0000-0000-000000000001",
                "batch_number": "BATCH-001",
                "expiry_date": "2028-12-31",
                "purchase_price": "1.00",
                "sale_price": "2.00",
                "quantity_received": "10",
            },
        )
        self.assertEqual(duplicate_receipt.status_code, 302)
        self.assertEqual(
            MedicineBatch.objects.filter(batch_number="BATCH-001").count(), 1
        )

        response = self.client.post(
            reverse("dispense_prescription", args=[self.prescription.pk]),
            {
                "prescription_item": self.item.pk,
                "batch": batch.pk,
                "quantity": "2",
                "request_key": "00000000-0000-0000-0000-000000000002",
            },
        )

        self.assertEqual(response.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("8"))
        self.assertTrue(
            Dispensing.objects.filter(
                prescription=self.prescription,
                lines__prescription_item=self.item,
            ).exists()
        )

    def test_duplicate_dispense_is_idempotent_and_links_invoice(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=StockReceipt.objects.create(
                number="IDEMPOTENT-RECEIPT",
                supplier=self.supplier,
                received_at=timezone.now(),
            ),
            batch_number="IDEMPOTENT-BATCH",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("10"),
            quantity_on_hand=Decimal("10"),
        )
        self.client.force_login(self.pharmacy)
        payload = {
            "prescription_item": self.item.pk,
            "batch": batch.pk,
            "quantity": "2",
            "request_key": "00000000-0000-0000-0000-000000000008",
        }
        url = reverse("dispense_prescription", args=[self.prescription.pk])

        first = self.client.post(url, payload)
        duplicate = self.client.post(url, payload)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(duplicate.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("8"))
        dispensing = Dispensing.objects.get(prescription=self.prescription)
        self.assertEqual(dispensing.invoice.total, Decimal("4.00"))
        self.assertEqual(
            StockMovement.objects.filter(
                request_key="00000000-0000-0000-0000-000000000008"
            ).count(),
            1,
        )

    def test_otc_sale_return_and_admin_refund_share_invoice_ledger(self):
        self.medicine.is_otc = True
        self.medicine.save(update_fields=("is_otc", "updated_at"))
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=StockReceipt.objects.create(
                number="OTC-RECEIPT",
                supplier=self.supplier,
                received_at=timezone.now(),
            ),
            batch_number="OTC-BATCH",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("10"),
            quantity_on_hand=Decimal("10"),
        )
        self.client.force_login(self.pharmacy)

        sale_response = self.client.post(
            reverse("pharmacy_sale_create"),
            {
                "batch": batch.pk,
                "quantity": "2",
                "request_key": "00000000-0000-0000-0000-000000000009",
            },
        )
        self.assertEqual(sale_response.status_code, 302)
        sale_detail = self.client.get(sale_response.url)
        self.assertEqual(sale_detail.status_code, 200)
        sale = PharmacySale.objects.get()
        invoice = sale.invoice
        self.assertIsNone(invoice.patient)
        self.assertEqual(invoice.total, Decimal("4.00"))
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("8"))

        sale_line = sale.lines.get()
        return_response = self.client.post(
            reverse("pharmacy_return_create"),
            {
                "sale_line": sale_line.pk,
                "quantity": "1",
                "reason": "Synthetic unopened return",
                "request_key": "00000000-0000-0000-0000-000000000010",
            },
        )
        self.assertEqual(return_response.status_code, 302)
        pharmacy_return = PharmacyReturn.objects.get()
        self.assertEqual(pharmacy_return.status, PharmacyReturn.Status.PENDING)
        self.assertEqual(pharmacy_return.lines.get().sale_line, sale_line)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("8"))

        method = PaymentMethod.objects.create(code="OTC-CASH", name="OTC Cash")
        payment = Payment.objects.create(
            receipt_number="OTC-RECEIPT-PAY",
            invoice=invoice,
            method=method,
            amount=Decimal("4.00"),
            received_at=timezone.now(),
        )
        administrator = get_user_model().objects.create_user(
            username="pharmacy-finance-administrator",
            password="Synthetic-Password-123!",
        )
        administrator.groups.add(Group.objects.get(name="Administrator"))
        StaffProfile.objects.create(
            user=administrator,
            employee_id="PHARM-ADMIN-001",
        )
        self.client.force_login(administrator)
        refund_response = self.client.post(
            reverse("invoice_refund", args=[invoice.pk]),
            {
                "payment": payment.pk,
                "pharmacy_return": pharmacy_return.pk,
                "amount": "2.00",
                "reason": "Approved synthetic return",
                "request_key": "00000000-0000-0000-0000-000000000021",
            },
        )

        self.assertEqual(refund_response.status_code, 302)
        pharmacy_return.refresh_from_db()
        self.assertEqual(pharmacy_return.status, PharmacyReturn.Status.APPROVED)
        self.assertEqual(pharmacy_return.refund.amount, Decimal("2.00"))
        duplicate_refund = self.client.post(
            reverse("invoice_refund", args=[invoice.pk]),
            {
                "payment": payment.pk,
                "pharmacy_return": pharmacy_return.pk,
                "amount": "2.00",
                "reason": "Approved synthetic return",
                "request_key": "00000000-0000-0000-0000-000000000021",
            },
        )
        self.assertEqual(duplicate_refund.status_code, 302)
        self.assertEqual(Refund.objects.filter(payment=payment).count(), 1)

    def test_otc_sales_require_approval_and_duplicate_posts_are_idempotent(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=StockReceipt.objects.create(
                number="OTC-GUARD-RECEIPT",
                supplier=self.supplier,
                received_at=timezone.now(),
            ),
            batch_number="OTC-GUARD-BATCH",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("5"),
            quantity_on_hand=Decimal("5"),
        )
        self.client.force_login(self.pharmacy)
        payload = {
            "batch": batch.pk,
            "quantity": "1",
            "request_key": "00000000-0000-0000-0000-000000000011",
        }

        rejected = self.client.post(reverse("pharmacy_sale_create"), payload)
        self.assertEqual(rejected.status_code, 400)
        self.medicine.is_otc = True
        self.medicine.save(update_fields=("is_otc", "updated_at"))
        first = self.client.post(reverse("pharmacy_sale_create"), payload)
        duplicate = self.client.post(reverse("pharmacy_sale_create"), payload)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(duplicate.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("4"))
        self.assertEqual(PharmacySale.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_admin_rejection_releases_return_quantity(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=StockReceipt.objects.create(
                number="RETURN-REJECT-RECEIPT",
                supplier=self.supplier,
                received_at=timezone.now(),
            ),
            batch_number="RETURN-REJECT-BATCH",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("5"),
            quantity_on_hand=Decimal("3"),
        )
        sale = PharmacySale.objects.create(
            number="RETURN-REJECT-SALE",
            status=PharmacySale.Status.ISSUED,
            sold_at=timezone.now(),
            sold_by=self.pharmacy_profile,
        )
        sale_line = PharmacySaleLine.objects.create(
            sale=sale,
            batch=batch,
            quantity=Decimal("2"),
            unit_price=Decimal("2.00"),
            line_total=Decimal("4.00"),
        )
        pharmacy_return = PharmacyReturn.objects.create(
            number="RETURN-REJECT-001",
            reason="Pending reason",
            status=PharmacyReturn.Status.PENDING,
            created_by=self.pharmacy_profile,
        )
        ReturnLine.objects.create(
            pharmacy_return=pharmacy_return,
            sale_line=sale_line,
            quantity=Decimal("1"),
            refund_amount=Decimal("2.00"),
        )
        administrator = get_user_model().objects.create_user(
            username="return-review-administrator",
            password="Synthetic-Password-123!",
        )
        administrator.groups.add(Group.objects.get(name="Administrator"))
        StaffProfile.objects.create(user=administrator, employee_id="RETURN-ADMIN-001")
        self.client.force_login(administrator)

        response = self.client.post(
            reverse("pharmacy_return_reject", args=[pharmacy_return.pk]),
            {"reason": "Packaging was opened"},
        )

        self.assertEqual(response.status_code, 302)
        pharmacy_return.refresh_from_db()
        self.assertEqual(pharmacy_return.status, PharmacyReturn.Status.REJECTED)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="pharmacy.return_rejected",
                target_id=str(pharmacy_return.pk),
                details__reason="Packaging was opened",
            ).exists()
        )
        self.client.force_login(self.pharmacy)
        replacement = self.client.post(
            reverse("pharmacy_return_create"),
            {
                "sale_line": sale_line.pk,
                "quantity": "1",
                "reason": "Retry after rejection",
                "request_key": "00000000-0000-0000-0000-000000000012",
            },
        )
        self.assertEqual(replacement.status_code, 302)
        self.assertEqual(
            PharmacyReturn.objects.filter(status=PharmacyReturn.Status.PENDING).count(),
            1,
        )

    def test_expired_batch_cannot_be_dispensed(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=StockReceipt.objects.create(
                number="EXPIRED-RECEIPT",
                supplier=self.supplier,
                received_at=timezone.now(),
            ),
            batch_number="EXPIRED-BATCH",
            expiry_date="2020-01-01",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("5"),
            quantity_on_hand=Decimal("5"),
        )
        self.client.force_login(self.pharmacy)

        response = self.client.post(
            reverse("dispense_prescription", args=[self.prescription.pk]),
            {
                "prescription_item": self.item.pk,
                "batch": batch.pk,
                "quantity": "1",
                "request_key": "00000000-0000-0000-0000-000000000003",
            },
        )

        self.assertEqual(response.status_code, 400)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("5"))
        self.assertFalse(
            Dispensing.objects.filter(prescription=self.prescription).exists()
        )

    def test_partial_dispensing_cannot_exceed_prescribed_total(self):
        receipt = StockReceipt.objects.create(
            number="PARTIAL-RECEIPT",
            supplier=self.supplier,
            received_at=timezone.now(),
        )
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=receipt,
            batch_number="PARTIAL-BATCH",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("20"),
            quantity_on_hand=Decimal("20"),
        )
        self.client.force_login(self.pharmacy)
        url = reverse("dispense_prescription", args=[self.prescription.pk])
        data = {"prescription_item": self.item.pk, "batch": batch.pk}

        first = self.client.post(
            url,
            {
                **data,
                "quantity": "6",
                "request_key": "00000000-0000-0000-0000-000000000004",
            },
        )
        second = self.client.post(
            url,
            {
                **data,
                "quantity": "5",
                "request_key": "00000000-0000-0000-0000-000000000005",
            },
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 400)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("14"))
        self.assertEqual(
            DispensingLine.objects.filter(prescription_item=self.item).aggregate(
                total=Sum("quantity")
            )["total"],
            Decimal("6"),
        )

    def test_stock_adjustment_requires_reason_and_records_movement(self):
        receipt = StockReceipt.objects.create(
            number="ADJUST-RECEIPT",
            supplier=self.supplier,
            received_at=timezone.now(),
        )
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=receipt,
            batch_number="ADJUST-BATCH",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("10"),
            quantity_on_hand=Decimal("10"),
        )
        self.client.force_login(self.pharmacy)

        response = self.client.post(
            reverse("stock_adjustment", args=[batch.pk]),
            {
                "quantity_delta": "2",
                "reason": "Synthetic count correction",
                "request_key": "00000000-0000-0000-0000-000000000006",
            },
        )

        self.assertEqual(response.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_on_hand, Decimal("12"))
        movement = StockMovement.objects.get(
            batch=batch, kind=StockMovement.Kind.ADJUSTMENT
        )
        self.assertEqual(movement.quantity_after, Decimal("12"))
        audit = AuditEvent.objects.get(action="stock.adjusted", target_id=str(batch.pk))
        self.assertEqual(movement.reference_id, str(audit.pk))
        self.assertEqual(audit.details["reason"], "Synthetic count correction")

    def test_quarantined_batch_cannot_be_dispensed(self):
        receipt = StockReceipt.objects.create(
            number="QUARANTINE-RECEIPT",
            supplier=self.supplier,
            received_at=timezone.now(),
        )
        batch = MedicineBatch.objects.create(
            medicine=self.medicine,
            receipt=receipt,
            batch_number="QUARANTINE-BATCH",
            expiry_date="2028-12-31",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=Decimal("5"),
            quantity_on_hand=Decimal("5"),
            is_quarantined=True,
        )
        self.client.force_login(self.pharmacy)

        response = self.client.post(
            reverse("dispense_prescription", args=[self.prescription.pk]),
            {
                "prescription_item": self.item.pk,
                "batch": batch.pk,
                "quantity": "1",
                "request_key": "00000000-0000-0000-0000-000000000007",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Dispensing.objects.filter(prescription=self.prescription).exists()
        )

    def test_fefo_suggestions_exclude_expired_and_quarantined_batches(self):
        receipt = StockReceipt.objects.create(
            number="FEFO-RECEIPT",
            supplier=self.supplier,
            received_at=timezone.now(),
        )
        for batch_number, expiry_date, quarantined in (
            ("FEFO-LATE", "2028-12-31", False),
            ("FEFO-EARLY", "2027-01-01", False),
            ("FEFO-EXPIRED", "2020-01-01", False),
            ("FEFO-QUARANTINED", "2027-02-01", True),
        ):
            MedicineBatch.objects.create(
                medicine=self.medicine,
                receipt=receipt,
                batch_number=batch_number,
                expiry_date=expiry_date,
                purchase_price=Decimal("1.00"),
                sale_price=Decimal("2.00"),
                quantity_received=Decimal("5"),
                quantity_on_hand=Decimal("5"),
                is_quarantined=quarantined,
            )
        self.client.force_login(self.pharmacy)

        response = self.client.get(reverse("pharmacy_prescription_list"))

        self.assertEqual(response.status_code, 200)
        prescription = next(
            row
            for row in response.context["prescriptions"]
            if row.pk == self.prescription.pk
        )
        suggested = list(prescription.items.all()[0].available_batches)
        self.assertEqual(
            [batch.batch_number for batch in suggested], ["FEFO-EARLY", "FEFO-LATE"]
        )
        self.assertContains(response, "(FEFO)")


class RolePermissionTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)

    def test_each_role_has_only_its_approved_model_permissions(self):
        matrix = {
            "Reception": (
                {"add_patient", "add_appointment", "add_payment"},
                {"view_consultation", "add_refund", "add_medicine"},
            ),
            "Pharmacy": (
                {
                    "view_prescription",
                    "add_stockreceipt",
                    "add_dispensing",
                    "adjust_stock",
                },
                {"add_appointment", "add_consultation", "change_patient"},
            ),
            "Doctor": (
                {"view_patient", "add_consultation", "add_prescription"},
                {"add_payment", "add_medicine", "approve_refund"},
            ),
            "Administrator": (
                {
                    "add_user",
                    "add_service",
                    "change_hospitalsettings",
                    "add_invoice",
                    "add_adjustment",
                    "add_refund",
                    "approve_refund",
                    "void_invoice",
                },
                {"view_patient", "view_consultation", "add_payment"},
            ),
        }

        for role, (allowed, denied) in matrix.items():
            with self.subTest(role=role):
                user = get_user_model().objects.create_user(
                    username=f"{role.lower()}-permission-test",
                    password="Synthetic-Password-123!",
                )
                user.groups.add(Group.objects.get(name=role))
                for codename in allowed:
                    self.assertTrue(
                        user.has_perm(f"core.{codename}")
                        or user.has_perm(f"auth.{codename}")
                    )
                for codename in denied:
                    self.assertFalse(
                        user.has_perm(f"core.{codename}")
                        or user.has_perm(f"auth.{codename}")
                    )

    def test_doctor_patient_access_is_limited_to_assigned_patients(self):
        doctor_user = get_user_model().objects.create_user(
            username="scoped-doctor", password="Synthetic-Password-123!"
        )
        doctor_user.groups.add(Group.objects.get(name="Doctor"))
        department = Department.objects.create(code="DOC", name="Synthetic Department")
        doctor = StaffProfile.objects.create(
            user=doctor_user, employee_id="DOC-001", department=department
        )
        other_user = get_user_model().objects.create_user(username="other-doctor")
        other_doctor = StaffProfile.objects.create(
            user=other_user, employee_id="DOC-002", department=department
        )
        visit_type = VisitType.objects.create(code="VISIT", name="Synthetic Visit")
        assigned = Patient.objects.create(mrn="SCOPE-001", full_name="Assigned Patient")
        unrelated = Patient.objects.create(
            mrn="SCOPE-002", full_name="Unrelated Patient"
        )
        Appointment.objects.create(
            patient=assigned,
            doctor=doctor,
            visit_type=visit_type,
            scheduled_at="2026-12-01T09:00:00Z",
        )
        Appointment.objects.create(
            patient=unrelated,
            doctor=other_doctor,
            visit_type=visit_type,
            scheduled_at="2026-12-01T10:00:00Z",
        )

        self.assertEqual(
            list(doctor_patient_queryset(doctor_user).values_list("pk", flat=True)),
            [assigned.pk],
        )

    def test_administrator_cannot_escalate_self_to_superuser(self):
        administrator = get_user_model().objects.create_user(
            username="role-admin",
            password="Synthetic-Password-123!",
            is_staff=True,
        )
        administrator.groups.add(Group.objects.get(name="Administrator"))
        self.client.force_login(administrator)

        add_url = reverse("admin:auth_user_add")
        response = self.client.get(add_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="is_superuser"')
        self.assertNotContains(response, 'name="user_permissions"')

        response = self.client.post(
            add_url,
            {
                "username": "attempted-superuser",
                "password1": "Synthetic-New-Password-123!",
                "password2": "Synthetic-New-Password-123!",
                "is_superuser": "on",
                "is_staff": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="attempted-superuser")
        self.assertFalse(created.is_superuser)
        self.assertFalse(created.user_permissions.exists())


class PatientWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.reception = get_user_model().objects.create_user(
            username="patient-reception", password="Synthetic-Password-123!"
        )
        self.reception.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(
            user=self.reception, employee_id="PAT-RECEPTION-001"
        )

    def test_reception_can_register_with_generated_identifier(self):
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("patient_create"),
            {
                "full_name": "Synthetic Patient One",
                "date_of_birth": "1990-01-02",
                "phone": "5550100",
                "address": "Synthetic Address",
                "emergency_contact_name": "Synthetic Contact",
                "emergency_contact_phone": "5550101",
                "allergy_safety_notes": "must not be accepted from reception",
            },
        )

        patient = Patient.objects.get(full_name="Synthetic Patient One")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(patient.mrn, "1")
        self.assertEqual(patient.allergy_safety_notes, "")
        event = AuditEvent.objects.get(
            action="patient.created", target_id=str(patient.pk)
        )
        self.assertEqual(event.actor, self.reception.staff_profile)
        self.assertIn("full_name", event.details["changed_fields"])
        self.assertNotIn("Synthetic Patient One", str(event.details))

    def test_exact_name_and_phone_duplicate_warns_but_never_merges(self):
        existing = Patient.objects.create(
            mrn="EXISTING-001", full_name="Synthetic Patient", phone="5550110"
        )
        self.client.force_login(self.reception)
        data = {
            "full_name": "Synthetic Patient",
            "phone": "5550110",
            "address": "",
            "emergency_contact_name": "",
            "emergency_contact_phone": "",
        }

        warning = self.client.post(reverse("patient_create"), data)
        self.assertEqual(warning.status_code, 200)
        self.assertContains(warning, "Possible duplicate patient")
        self.assertEqual(Patient.objects.count(), 1)

        data["confirm_duplicate"] = "yes"
        created = self.client.post(reverse("patient_create"), data)
        self.assertEqual(created.status_code, 302)
        self.assertEqual(Patient.objects.count(), 2)
        existing.refresh_from_db()
        self.assertEqual(existing.mrn, "EXISTING-001")

    def test_search_matches_patient_identifier_name_and_phone(self):
        patient = Patient.objects.create(
            mrn="SEARCH-001", full_name="Synthetic Search Patient", phone="5550123"
        )
        self.client.force_login(self.reception)

        for query in ("SEARCH-001", "Search Patient", "5550123"):
            with self.subTest(query=query):
                response = self.client.get(reverse("patient_list"), {"q": query})
                self.assertContains(response, patient.mrn)

    def test_reception_can_update_demographics_but_not_safety_notes(self):
        patient = Patient.objects.create(
            mrn="EDIT-001",
            full_name="Original Name",
            phone="5550130",
            allergy_safety_notes="Synthetic confidential note",
        )
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("patient_update", args=[patient.pk]),
            {
                "full_name": "Updated Name",
                "phone": "5550131",
                "address": "Updated Synthetic Address",
                "emergency_contact_name": "",
                "emergency_contact_phone": "",
                "allergy_safety_notes": "Unauthorized change",
            },
        )

        patient.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(patient.full_name, "Updated Name")
        self.assertEqual(patient.allergy_safety_notes, "Synthetic confidential note")
        detail = self.client.get(reverse("patient_detail", args=[patient.pk]))
        self.assertNotContains(detail, "Synthetic confidential note")
        event = AuditEvent.objects.get(
            action="patient.demographics_updated", target_id=str(patient.pk)
        )
        self.assertEqual(event.actor, self.reception.staff_profile)
        self.assertIn("full_name", event.details["changed_fields"])
        self.assertNotIn("Updated Name", str(event.details))

    def test_future_date_of_birth_is_rejected(self):
        form = PatientForm(
            data={
                "full_name": "Synthetic Patient",
                "date_of_birth": "2999-01-01",
                "phone": "",
                "address": "",
                "emergency_contact_name": "",
                "emergency_contact_phone": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("date_of_birth", form.errors)

    def test_doctor_can_only_open_assigned_patient_and_cannot_edit(self):
        department = Department.objects.create(code="PAT-DOC", name="Synthetic Dept")
        doctor = get_user_model().objects.create_user(
            username="patient-doctor", password="Synthetic-Password-123!"
        )
        doctor.groups.add(Group.objects.get(name="Doctor"))
        doctor_profile = StaffProfile.objects.create(
            user=doctor, employee_id="PAT-DOC-001", department=department
        )
        other_doctor = get_user_model().objects.create_user(
            username="patient-other-doctor"
        )
        other_profile = StaffProfile.objects.create(
            user=other_doctor, employee_id="PAT-DOC-002", department=department
        )
        visit_type = VisitType.objects.create(code="PAT-VISIT", name="Patient Visit")
        assigned = Patient.objects.create(mrn="ASSIGNED-001", full_name="Assigned")
        unrelated = Patient.objects.create(mrn="UNRELATED-001", full_name="Unrelated")
        Appointment.objects.create(
            patient=assigned,
            doctor=doctor_profile,
            visit_type=visit_type,
            scheduled_at="2026-12-02T09:00:00Z",
        )
        Appointment.objects.create(
            patient=unrelated,
            doctor=other_profile,
            visit_type=visit_type,
            scheduled_at="2026-12-02T10:00:00Z",
        )
        self.client.force_login(doctor)

        self.assertEqual(
            self.client.get(reverse("patient_detail", args=[assigned.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("patient_detail", args=[unrelated.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("patient_update", args=[assigned.pk])).status_code,
            403,
        )

    def test_pharmacy_and_administrator_cannot_open_patient_directory(self):
        for role in ("Pharmacy", "Administrator"):
            user = get_user_model().objects.create_user(
                username=f"patient-{role.lower()}", password="Synthetic-Password-123!"
            )
            user.groups.add(Group.objects.get(name=role))
            self.client.force_login(user)
            with self.subTest(role=role):
                self.assertEqual(
                    self.client.get(reverse("patient_list")).status_code, 403
                )
                self.assertEqual(
                    self.client.post(reverse("patient_create")).status_code, 403
                )

    def test_patient_data_is_not_permanently_deletable_through_ui(self):
        patient = Patient.objects.create(mrn="KEEP-001", full_name="Keep Record")
        self.client.force_login(self.reception)

        response = self.client.post(f"/patients/{patient.pk}/delete/")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Patient.objects.filter(pk=patient.pk).exists())


class AppointmentWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.reception = get_user_model().objects.create_user(
            username="appointment-reception",
            password="Synthetic-Password-123!",
        )
        self.reception.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(
            user=self.reception, employee_id="APPT-RECEPTION-001"
        )
        self.doctor = get_user_model().objects.create_user(
            username="appointment-doctor", password="Synthetic-Password-123!"
        )
        self.doctor.groups.add(Group.objects.get(name="Doctor"))
        self.doctor_profile = StaffProfile.objects.create(
            user=self.doctor, employee_id="APPT-DOCTOR-001"
        )
        self.other_doctor = get_user_model().objects.create_user(
            username="appointment-other-doctor"
        )
        self.other_profile = StaffProfile.objects.create(
            user=self.other_doctor, employee_id="APPT-DOCTOR-002"
        )
        self.patient = Patient.objects.create(
            mrn="APPT-PATIENT-001", full_name="Synthetic Appointment Patient"
        )
        self.visit_type = VisitType.objects.create(
            code="APPT-VISIT", name="Synthetic Appointment Visit"
        )

    def make_appointment(
        self,
        *,
        doctor=None,
        patient=None,
        hour=9,
        status=Appointment.Status.SCHEDULED,
    ):
        return Appointment.objects.create(
            patient=patient or self.patient,
            doctor=doctor or self.doctor_profile,
            visit_type=self.visit_type,
            scheduled_at=f"2026-12-03T{hour:02}:00:00Z",
            status=status,
        )

    def test_reception_books_appointment_with_server_controlled_status(self):
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_create"),
            {
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T14:30",
                "status": "completed",
            },
        )

        appointment = Appointment.objects.get(patient=self.patient)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.status, Appointment.Status.SCHEDULED)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="appointment.created", target_id=str(appointment.pk)
            ).exists()
        )

    def test_exact_active_doctor_slot_conflict_is_rejected(self):
        self.make_appointment()
        form = AppointmentForm(
            data={
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T14:30",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("scheduled_at", form.errors)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_appointment()

    def test_thirty_minute_overlap_is_rejected_but_back_to_back_is_allowed(self):
        self.make_appointment(hour=9)
        other_patient = Patient.objects.create(
            mrn="APPT-OVERLAP-002", full_name="Overlap Synthetic Patient"
        )
        form_data = {
            "patient": other_patient.pk,
            "doctor": self.doctor_profile.pk,
            "visit_type": self.visit_type.pk,
            "scheduled_at": "2026-12-03T14:45",
        }

        overlap = AppointmentForm(data=form_data)
        back_to_back = AppointmentForm(
            data={**form_data, "scheduled_at": "2026-12-03T15:00"}
        )

        self.assertFalse(overlap.is_valid())
        self.assertIn("scheduled_at", overlap.errors)
        self.assertTrue(back_to_back.is_valid(), back_to_back.errors)

    def test_create_and_reschedule_reject_overlapping_slots(self):
        self.make_appointment(hour=9)
        other_patient = Patient.objects.create(
            mrn="APPT-OVERLAP-003", full_name="Second Overlap Patient"
        )
        moving = self.make_appointment(hour=11, patient=other_patient)
        self.client.force_login(self.reception)
        data = {
            "patient": other_patient.pk,
            "doctor": self.doctor_profile.pk,
            "visit_type": self.visit_type.pk,
            "scheduled_at": "2026-12-03T14:45",
        }

        create_response = self.client.post(reverse("appointment_create"), data)
        reschedule_response = self.client.post(
            reverse("appointment_reschedule", args=[moving.pk]), data
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(reschedule_response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 2)
        moving.refresh_from_db()
        self.assertEqual(moving.scheduled_at.hour, 11)

    def test_reception_can_reschedule_and_change_is_audited(self):
        appointment = self.make_appointment()
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_reschedule", args=[appointment.pk]),
            {
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T16:30",
            },
        )

        appointment.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.scheduled_at.hour, 11)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="appointment.rescheduled", target_id=str(appointment.pk)
            ).exists()
        )

    def test_reschedule_into_occupied_slot_shows_conflict(self):
        appointment = self.make_appointment()
        other_patient = Patient.objects.create(
            mrn="APPT-CONFLICT-002", full_name="Conflict Synthetic Patient"
        )
        self.make_appointment(patient=other_patient, hour=10)
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_reschedule", args=[appointment.pk]),
            {
                "patient": self.patient.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": "2026-12-03T15:30",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overlapping active appointment")

    def test_doctor_schedule_contains_only_own_appointments(self):
        own = self.make_appointment()
        other_patient = Patient.objects.create(
            mrn="APPT-PATIENT-002", full_name="Other Synthetic Patient"
        )
        other = self.make_appointment(
            doctor=self.other_profile, patient=other_patient, hour=10
        )
        self.client.force_login(self.doctor)

        response = self.client.get(reverse("appointment_list"), {"date": "2026-12-03"})

        self.assertContains(response, own.patient.mrn)
        self.assertNotContains(response, other.patient.mrn)

    def test_check_in_start_complete_and_audit(self):
        appointment = self.make_appointment()
        self.client.force_login(self.reception)
        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "check_in"},
        )
        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CHECKED_IN)
        self.assertIsNotNone(appointment.checked_in_at)

        self.client.force_login(self.doctor)
        self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "start"},
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.IN_PROGRESS)
        self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "complete"},
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)
        self.assertIsNotNone(appointment.completed_at)
        self.assertEqual(
            AuditEvent.objects.filter(
                action="appointment.status_changed", target_id=str(appointment.pk)
            ).count(),
            3,
        )

    def test_reception_can_mark_no_show_and_timestamp_it(self):
        appointment = self.make_appointment()
        self.client.force_login(self.reception)

        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "no_show"},
        )

        appointment.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.status, Appointment.Status.NO_SHOW)
        self.assertIsNotNone(appointment.no_show_at)

    def test_invalid_transition_and_cross_doctor_post_are_rejected(self):
        appointment = self.make_appointment(doctor=self.other_profile)
        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "start"},
        )
        self.assertEqual(response.status_code, 404)

        appointment.doctor = self.doctor_profile
        appointment.save(update_fields=("doctor", "updated_at"))
        response = self.client.post(
            reverse("appointment_transition", args=[appointment.pk]),
            {"action": "complete"},
        )
        self.assertEqual(response.status_code, 400)

    def test_queue_is_ordered_by_check_in_time(self):
        first = self.make_appointment(hour=10, status=Appointment.Status.CHECKED_IN)
        second_patient = Patient.objects.create(
            mrn="APPT-QUEUE-002", full_name="Second Queue Patient"
        )
        second = self.make_appointment(
            patient=second_patient, hour=11, status=Appointment.Status.CHECKED_IN
        )
        Appointment.objects.filter(pk=first.pk).update(
            checked_in_at="2026-12-03T09:20:00Z"
        )
        Appointment.objects.filter(pk=second.pk).update(
            checked_in_at="2026-12-03T09:10:00Z"
        )
        self.client.force_login(self.reception)

        response = self.client.get(reverse("appointment_list"), {"date": "2026-12-03"})

        queue_html = response.content.decode().split("<h2>Waiting queue</h2>", 1)[1]
        self.assertLess(
            queue_html.index(second.patient.mrn), queue_html.index(first.patient.mrn)
        )

    def test_pharmacy_cannot_view_or_change_appointments(self):
        pharmacy = get_user_model().objects.create_user(username="appointment-pharmacy")
        pharmacy.groups.add(Group.objects.get(name="Pharmacy"))
        appointment = self.make_appointment()
        self.client.force_login(pharmacy)

        self.assertEqual(self.client.get(reverse("appointment_list")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("appointment_transition", args=[appointment.pk]),
                {"action": "cancel"},
            ).status_code,
            403,
        )


class ClinicalWorkflowTests(TestCase):
    def setUp(self):
        call_command("bootstrap_hospital", stdout=None)
        self.doctor = get_user_model().objects.create_user(
            username="clinical-doctor", password="Synthetic-Password-123!"
        )
        self.doctor.groups.add(Group.objects.get(name="Doctor"))
        self.doctor_profile = StaffProfile.objects.create(
            user=self.doctor, employee_id="CLINICAL-DOC-001"
        )
        self.other_doctor = get_user_model().objects.create_user(
            username="clinical-other-doctor"
        )
        self.other_profile = StaffProfile.objects.create(
            user=self.other_doctor, employee_id="CLINICAL-DOC-002"
        )
        self.reception = get_user_model().objects.create_user(
            username="clinical-reception"
        )
        self.reception.groups.add(Group.objects.get(name="Reception"))
        self.pharmacy = get_user_model().objects.create_user(
            username="clinical-pharmacy"
        )
        self.pharmacy.groups.add(Group.objects.get(name="Pharmacy"))
        self.patient = Patient.objects.create(
            mrn="CLINICAL-PATIENT-001",
            full_name="Synthetic Clinical Patient",
            allergy_safety_notes="Synthetic allergy warning",
        )
        visit_type = VisitType.objects.create(
            code="CLINICAL-VISIT", name="Clinical Visit"
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor_profile,
            visit_type=visit_type,
            scheduled_at="2026-12-04T09:00:00Z",
            status=Appointment.Status.IN_PROGRESS,
        )
        self.medicine = Medicine.objects.create(
            code="CLINICAL-MED-001",
            generic_name="Synthetic Medicine",
            strength="10 mg",
            unit="tablet",
        )

    def prescription_post_data(self, **overrides):
        data = {
            "clinical_notes": "Synthetic consultation notes",
            "diagnosis": "Synthetic diagnosis",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-medicine": str(self.medicine.pk),
            "items-0-dosage": "1 tablet",
            "items-0-frequency": "twice daily",
            "items-0-duration": "5 days",
            "items-0-instructions": "Synthetic instructions",
            "items-0-quantity": "10",
        }
        data.update(overrides)
        return data

    def test_doctor_creates_consultation_and_issued_prescription(self):
        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse("consultation_create", args=[self.appointment.pk]),
            self.prescription_post_data(),
        )

        consultation = Consultation.objects.get(appointment=self.appointment)
        prescription = Prescription.objects.get(consultation=consultation)
        item = prescription.items.get()
        self.assertRedirects(
            response, reverse("consultation_detail", args=[consultation.pk])
        )
        self.assertEqual(consultation.doctor, self.doctor_profile)
        self.assertEqual(consultation.patient, self.patient)
        self.assertEqual(prescription.number, "1")
        self.assertEqual(prescription.status, Prescription.Status.ISSUED)
        self.assertEqual(item.quantity, Decimal("10"))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.consultation_created",
                target_id=str(consultation.pk),
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.prescription_issued",
                target_id=str(prescription.pk),
            ).exists()
        )

    def test_doctor_can_record_simple_follow_up_plan(self):
        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse("consultation_create", args=[self.appointment.pk]),
            self.prescription_post_data(
                follow_up_date="2026-12-18",
                follow_up_note="Review symptoms in two weeks",
            ),
        )

        consultation = Consultation.objects.get(appointment=self.appointment)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(consultation.follow_up_date.isoformat(), "2026-12-18")
        self.assertEqual(consultation.follow_up_note, "Review symptoms in two weeks")
        self.assertContains(
            self.client.get(reverse("consultation_detail", args=[consultation.pk])),
            "Review symptoms in two weeks",
        )

    def test_duplicate_submission_reuses_existing_encounter(self):
        self.client.force_login(self.doctor)
        url = reverse("consultation_create", args=[self.appointment.pk])
        self.client.post(url, self.prescription_post_data())

        response = self.client.post(
            url,
            self.prescription_post_data(
                clinical_notes="Duplicate synthetic note",
                diagnosis="Duplicate synthetic diagnosis",
            ),
        )

        self.assertEqual(
            Consultation.objects.filter(appointment=self.appointment).count(), 1
        )
        self.assertRedirects(
            response,
            reverse(
                "consultation_detail",
                args=[Consultation.objects.get(appointment=self.appointment).pk],
            ),
        )

    def test_doctor_cannot_open_another_doctors_appointment(self):
        other_appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.other_profile,
            visit_type=self.appointment.visit_type,
            scheduled_at="2026-12-04T10:00:00Z",
            status=Appointment.Status.IN_PROGRESS,
        )
        self.client.force_login(self.doctor)

        response = self.client.get(
            reverse("consultation_create", args=[other_appointment.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_clinical_history_shows_only_notes_authored_by_current_doctor(self):
        own = Consultation.objects.create(
            appointment=self.appointment,
            patient=self.patient,
            doctor=self.doctor_profile,
            clinical_notes="Own synthetic clinical note",
            diagnosis="Own synthetic diagnosis",
        )
        Consultation.objects.create(
            patient=self.patient,
            doctor=self.other_profile,
            clinical_notes="Other doctor confidential note",
            diagnosis="Other doctor diagnosis",
        )
        self.client.force_login(self.doctor)

        response = self.client.get(reverse("clinical_history", args=[self.patient.pk]))

        self.assertContains(response, "Own synthetic diagnosis")
        self.assertNotContains(response, "Other doctor diagnosis")
        detail = self.client.get(reverse("consultation_detail", args=[own.pk]))
        self.assertContains(detail, "Own synthetic clinical note")
        self.assertNotContains(detail, "Other doctor confidential note")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.history_viewed", target_id=str(self.patient.pk)
            ).exists()
        )

    def test_empty_consultation_is_rejected(self):
        self.client.force_login(self.doctor)
        response = self.client.post(
            reverse("consultation_create", args=[self.appointment.pk]),
            {
                "clinical_notes": "",
                "diagnosis": "",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Consultation.objects.count(), 0)

    def test_reception_and_pharmacy_cannot_read_or_write_clinical_records(self):
        for user in (self.reception, self.pharmacy):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(
                    self.client.get(
                        reverse("consultation_create", args=[self.appointment.pk])
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.get(
                        reverse("clinical_history", args=[self.patient.pk])
                    ).status_code,
                    403,
                )

    def test_administrator_finance_scope_does_not_grant_operational_or_clinical_access(
        self,
    ):
        administrator = get_user_model().objects.create_user(
            username="clinical-scope-administrator",
            password="Synthetic-Password-123!",
        )
        administrator.groups.add(Group.objects.get(name="Administrator"))
        StaffProfile.objects.create(
            user=administrator,
            employee_id="CLINICAL-SCOPE-ADMIN",
        )
        consultation = Consultation.objects.create(
            appointment=self.appointment,
            patient=self.patient,
            doctor=self.doctor_profile,
            clinical_notes="Private synthetic note",
            diagnosis="Private synthetic diagnosis",
        )
        self.client.force_login(administrator)

        self.assertEqual(self.client.get(reverse("invoice_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("patient_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("appointment_list")).status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("clinical_history", args=[self.patient.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("consultation_detail", args=[consultation.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("consultation_create", args=[self.appointment.pk]),
                {"clinical_notes": "Unauthorized", "diagnosis": "Unauthorized"},
            ).status_code,
            403,
        )

    def test_pharmacy_sees_only_prescription_and_safety_data(self):
        consultation = Consultation.objects.create(
            appointment=self.appointment,
            patient=self.patient,
            doctor=self.doctor_profile,
            clinical_notes="Confidential synthetic clinical note",
            diagnosis="Confidential synthetic diagnosis",
        )
        prescription = Prescription.objects.create(
            number="CLINICAL-RX-001",
            consultation=consultation,
            patient=self.patient,
            doctor=self.doctor_profile,
            status=Prescription.Status.ISSUED,
        )
        prescription.items.create(
            medicine=self.medicine,
            dosage="1 tablet",
            frequency="daily",
            duration="5 days",
            instructions="Synthetic instructions",
            quantity=Decimal("5"),
        )
        self.client.force_login(self.pharmacy)

        queue = self.client.get(reverse("pharmacy_prescription_list"))
        printed = self.client.get(reverse("prescription_print", args=[prescription.pk]))

        for response in (queue, printed):
            self.assertContains(response, "Synthetic allergy warning")
            self.assertContains(response, "Synthetic Medicine")
            self.assertNotContains(response, "Confidential synthetic clinical note")
            self.assertNotContains(response, "Confidential synthetic diagnosis")

        self.assertEqual(
            self.client.get(
                reverse("consultation_detail", args=[consultation.pk])
            ).status_code,
            403,
        )

    def test_pharmacy_cannot_print_unissued_prescription(self):
        prescription = Prescription.objects.create(
            number="CLINICAL-DRAFT-001",
            patient=self.patient,
            doctor=self.doctor_profile,
            status=Prescription.Status.DRAFT,
        )
        self.client.force_login(self.pharmacy)

        response = self.client.get(
            reverse("prescription_print", args=[prescription.pk])
        )

        self.assertEqual(response.status_code, 404)
