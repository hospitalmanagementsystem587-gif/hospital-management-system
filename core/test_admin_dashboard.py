"""Tests for KAN-39 Admin Management Dashboard.

Verifies:
1. Authorized admin access (staff and superuser) on admin portal host.
2. Unauthenticated access follows established login redirect behavior.
3. Authenticated non-admin denial (Doctor, Reception, Pharmacy, Patient, ordinary users).
4. Wrong-portal behavior / fail-closed isolation.
5. Required dashboard content rendering (executive hero, KPI cards, operational summaries, quick links).
6. Metric correctness against known fixtures (patients, collections, refunds, beds, admissions, stock, feedback).
7. Empty database / empty-state behavior (safe degradation to 0/0.00 and accessible empty state presentation).
8. Template inheritance and component reuse from KAN-38 shared design system.
9. HTML escaping for user-controlled content (e.g. hospital name).
10. Existing route-name compatibility (admin:index, changelists).
11. Bounded query count performance during dashboard rendering.
"""

from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Admission,
    Appointment,
    Bed,
    Department,
    HospitalSettings,
    Invoice,
    Medicine,
    MedicineBatch,
    Patient,
    PatientAccount,
    PatientFeedback,
    Payment,
    PaymentMethod,
    Prescription,
    Refund,
    StaffProfile,
    Supplier,
    VisitType,
    Ward,
)

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
class AdminManagementDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create core groups
        cls.admin_group, _ = Group.objects.get_or_create(name="Administrator")
        cls.doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        cls.reception_group, _ = Group.objects.get_or_create(name="Reception")
        cls.pharmacy_group, _ = Group.objects.get_or_create(name="Pharmacy")

        # Hospital settings singleton
        cls.hospital, _ = HospitalSettings.objects.get_or_create(
            pk=1,
            defaults={"name": "Apollo General Hospital"},
        )

        # Users
        cls.superuser = User.objects.create_superuser(
            username="super_admin", email="super@hms.test", password="Password123!"
        )
        cls.staff_admin = User.objects.create_user(
            username="staff_admin", email="admin@hms.test", password="Password123!", is_staff=True
        )
        cls.staff_admin.groups.add(cls.admin_group)

        cls.doctor_user = User.objects.create_user(
            username="doc_smith", email="smith@hms.test", password="Password123!"
        )
        cls.doctor_user.groups.add(cls.doctor_group)

        cls.reception_user = User.objects.create_user(
            username="rec_jane", email="jane@hms.test", password="Password123!"
        )
        cls.reception_user.groups.add(cls.reception_group)

        cls.pharmacy_user = User.objects.create_user(
            username="pharm_bob", email="bob@hms.test", password="Password123!"
        )
        cls.pharmacy_user.groups.add(cls.pharmacy_group)

        cls.ordinary_user = User.objects.create_user(
            username="plain_user", email="plain@hms.test", password="Password123!"
        )

        # Department & Staff Profiles
        cls.dept = Department.objects.create(code="MED", name="General Medicine")
        cls.doc_profile = StaffProfile.objects.create(
            user=cls.doctor_user, employee_id="EMP001", department=cls.dept, job_title="Physician"
        )
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.staff_admin, employee_id="EMP002", department=cls.dept, job_title="Administrator"
        )

        # Patient & Account
        cls.patient = Patient.objects.create(
            mrn="MRN-0001",
            full_name="Aarav Sharma",
            date_of_birth="1990-01-01",
            phone="9876543210",
        )
        cls.patient_user = User.objects.create_user(
            username="aarav_patient", email="aarav@patient.test", password="Password123!"
        )
        cls.patient_account = PatientAccount.objects.create(
            user=cls.patient_user,
            patient=cls.patient,
            is_verified=True,
            email_verified=True,
        )

    def test_unauthenticated_access_redirects_to_login(self):
        """Unauthenticated requests to admin portal redirect to login with next parameter."""
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/?next=/admin/", response.url)

    def test_authenticated_non_admin_denied_access(self):
        """Non-staff users (doctor, reception, pharmacy, patient, ordinary) receive 403 Forbidden."""
        for user in (
            self.doctor_user,
            self.reception_user,
            self.pharmacy_user,
            self.patient_user,
            self.ordinary_user,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
                self.assertEqual(response.status_code, 403)

    def test_authorized_staff_admin_access(self):
        """Active staff user can access the admin dashboard at /admin/ on admin portal host."""
        self.client.force_login(self.staff_admin)
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Executive Management")
        self.assertContains(response, "Executive KPI Overview")
        self.assertContains(response, "Departmental & Operational Summary")
        self.assertContains(response, "Management Directory & System Registries")

    def test_authorized_superuser_access(self):
        """Active superuser can access the admin dashboard."""
        self.client.force_login(self.superuser)
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apollo General Hospital")

    def test_management_links_follow_model_permissions(self):
        """Quick actions are rendered only when Django grants the matching model permission."""
        self.client.force_login(self.staff_admin)
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertNotContains(response, 'href="/admin/core/department/"')
        self.assertNotContains(response, 'href="/admin/core/patientfeedback/"')

        self.staff_admin.user_permissions.add(
            Permission.objects.get(content_type__app_label="core", codename="view_department")
        )
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertContains(response, 'href="/admin/core/department/"')
        self.assertNotContains(response, 'href="/admin/core/patientfeedback/"')

    def test_wrong_portal_fail_closed_behavior(self):
        """Admin dashboard is only served on the admin portal; other portals maintain their boundaries."""
        self.client.force_login(self.doctor_user)
        # Doctor has access to staff portal, but is denied on admin portal
        res_admin = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(res_admin.status_code, 403)

        res_staff = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_staff.status_code, 200)

    def test_metrics_correctness_against_known_fixtures(self):
        """Metrics accurately aggregate patient, appointments, collections, refunds, IPD, and stock."""
        today = timezone.localdate()

        # 1. Appointments
        vt = VisitType.objects.create(code="NEW", name="New Consultation")
        apt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doc_profile,
            visit_type=vt,
            scheduled_at=timezone.now(),
            status=Appointment.Status.SCHEDULED,
        )

        # 2. Billing: Invoice, Payment, Refund
        pm = PaymentMethod.objects.create(code="CASH", name="Cash")
        inv = Invoice.objects.create(
            number="INV-001",
            patient=self.patient,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            created_by=self.admin_profile,
        )
        payment = Payment.objects.create(
            invoice=inv,
            method=pm,
            amount=Decimal("1500.00"),
            received_by=self.admin_profile,
            received_at=timezone.now(),
        )
        Refund.objects.create(
            payment=payment,
            amount=Decimal("200.00"),
            reason="Partial return",
            status=Refund.Status.ISSUED,
            requested_by=self.admin_profile,
        )

        # 3. IPD: Ward, Bed, Admission
        ward = Ward.objects.create(code="GEN", name="General Ward", floor=1)
        bed_occ = Bed.objects.create(ward=ward, bed_number="G-01", status=Bed.Status.OCCUPIED)
        Bed.objects.create(ward=ward, bed_number="G-02", status=Bed.Status.AVAILABLE)
        Admission.objects.create(
            admission_number="ADM-001",
            patient=self.patient,
            admitting_doctor=self.doc_profile,
            bed=bed_occ,
            status=Admission.Status.ADMITTED,
        )

        # 4. Pharmacy: Medicine, Batch, Prescription
        med = Medicine.objects.create(code="PARA500", generic_name="Paracetamol", brand_name="Crocin")
        supplier = Supplier.objects.create(code="SUP1", name="Apex Pharma")
        from core.models import StockReceipt
        receipt = StockReceipt.objects.create(
            number="REC-001",
            supplier=supplier,
            received_by=self.admin_profile,
            received_at=timezone.now(),
        )
        MedicineBatch.objects.create(
            medicine=med,
            receipt=receipt,
            batch_number="B123",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=100,
            quantity_on_hand=5,  # low stock < 10
            is_quarantined=False,
            expiry_date=today + timedelta(days=90),
        )
        MedicineBatch.objects.create(
            medicine=med,
            receipt=receipt,
            batch_number="BEXP",
            purchase_price=Decimal("1.00"),
            sale_price=Decimal("2.00"),
            quantity_received=50,
            quantity_on_hand=50,
            is_quarantined=False,
            expiry_date=today - timedelta(days=1),  # expired
        )
        Prescription.objects.create(
            number="RX-001",
            patient=self.patient,
            doctor=self.doc_profile,
            status=Prescription.Status.ISSUED,
        )

        # 5. Feedback
        PatientFeedback.objects.create(
            patient=self.patient,
            appointment=apt,
            doctor=self.doc_profile,
            rating=5,
            comment="Excellent care",
            status=PatientFeedback.Status.PENDING,
        )

        self.client.force_login(self.staff_admin)
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)

        # Verify KPI context values
        kpis = response.context["kpis"]
        self.assertEqual(kpis["total_patients"], 1)
        self.assertEqual(kpis["today_appointments"], 1)
        self.assertEqual(kpis["today_collections"], Decimal("1500.00"))
        self.assertEqual(kpis["today_refunds"], Decimal("200.00"))
        self.assertEqual(kpis["unsettled_invoices"], 1)
        self.assertEqual(kpis["active_admissions"], 1)
        self.assertEqual(kpis["occupied_beds"], 1)
        self.assertEqual(kpis["available_beds"], 1)
        self.assertEqual(kpis["total_beds"], 2)
        self.assertEqual(kpis["low_stock_batches"], 1)
        self.assertEqual(kpis["expired_batches"], 1)
        self.assertEqual(kpis["issued_prescriptions"], 1)
        self.assertEqual(kpis["pending_feedback"], 1)
        self.assertEqual(kpis["total_staff"], 2)

        # Verify rendered content reflects values
        self.assertContains(response, "₹1500.00")
        self.assertContains(response, "₹200.00")
        self.assertContains(response, "Occupied Beds")
        self.assertContains(response, "Available Beds")
        self.assertContains(response, "Low Stock Batches (<10 units)")
        self.assertContains(response, "Expired Batches")
        self.assertContains(response, "Feedback Awaiting Moderation")

    def test_empty_database_and_empty_state_behavior(self):
        """When optional data or records are empty, dashboard degrades gracefully without error."""
        # Archive the existing patient so active patient count is 0
        self.patient.archived_at = timezone.now()
        self.patient.save()

        self.client.force_login(self.superuser)
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)

        kpis = response.context["kpis"]
        self.assertEqual(kpis["total_patients"], 0)
        self.assertEqual(kpis["today_appointments"], 0)
        self.assertEqual(kpis["today_collections"], Decimal("0.00"))
        self.assertEqual(kpis["today_refunds"], Decimal("0.00"))
        self.assertEqual(kpis["unsettled_invoices"], 0)
        self.assertEqual(kpis["occupied_beds"], 0)
        self.assertEqual(kpis["available_beds"], 0)
        self.assertEqual(kpis["total_beds"], 0)
        self.assertEqual(kpis["low_stock_batches"], 0)
        self.assertEqual(kpis["expired_batches"], 0)
        self.assertEqual(kpis["issued_prescriptions"], 0)
        self.assertEqual(kpis["pending_feedback"], 0)

        # Empty state component rendered for beds
        self.assertContains(response, "No hospital beds configured")
        self.assertContains(response, "₹0.00")

    def test_template_inheritance_and_design_system_components(self):
        """Verify reuse of KAN-38 shared design system components and CSS styling."""
        self.client.force_login(self.staff_admin)
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)

        # Design system stylesheet linkage (accommodates ManifestStaticFilesStorage hashes)
        self.assertContains(response, "/static/core/style.")
        # Component classes
        self.assertContains(response, "hms-badge")
        self.assertContains(response, "hms-card")
        self.assertContains(response, "admin-kpi-card")
        self.assertContains(response, "admin-dashboard-hero")
        self.assertContains(response, "admin-quick-links-grid")

    def test_html_escaping_for_user_controlled_content(self):
        """Ensure malicious user-controlled content (e.g. hospital name) is properly escaped."""
        self.hospital.name = "<script>alert('xss')</script> Hospital"
        self.hospital.save()

        self.client.force_login(self.staff_admin)
        response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert('xss')</script>")
        self.assertContains(response, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt; Hospital")

    def test_query_count_performance_is_bounded(self):
        """Dashboard rendering does not introduce N+1 queries; query count remains strictly bounded."""
        self.client.force_login(self.staff_admin)
        # Warm up any internal caches / session setup
        self.client.get("/admin/", HTTP_HOST="admin.hms.test")

        with self.assertNumQueries(25):
            # Includes session fetch, user lookup, HospitalSettings singleton,
            # 14 bounded aggregate/count queries, and admin app_list model permissions
            response = self.client.get("/admin/", HTTP_HOST="admin.hms.test")
            self.assertEqual(response.status_code, 200)
