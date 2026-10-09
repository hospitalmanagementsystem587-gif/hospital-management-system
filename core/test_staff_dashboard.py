from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    Patient,
    StaffProfile,
    VisitType,
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
class StaffDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.doctor_user = User.objects.create_user("doctor_user", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC001",
        )

        cls.reception_user = User.objects.create_user("reception_user", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC001",
        )

        cls.pharmacy_user = User.objects.create_user("pharmacy_user", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM001",
        )

        cls.admin_user = User.objects.create_user("admin_user", password="password", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM001",
        )

        cls.ordinary_user = User.objects.create_user("ordinary_user", password="password")

    def test_anonymous_access_redirects_to_login(self):
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertRedirects(response, "/accounts/login/?next=/", fetch_redirect_response=False)

    def test_user_without_staff_role_forbidden(self):
        self.client.force_login(self.ordinary_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 403)

    def test_doctor_dashboard_role_scoping(self):
        self.client.force_login(self.doctor_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Doctor overview")
        self.assertNotContains(response, "Reception overview")
        self.assertNotContains(response, "Operations overview")
        self.assertNotContains(response, "Pharmacy overview")

    def test_reception_dashboard_role_scoping(self):
        self.client.force_login(self.reception_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reception overview")
        self.assertNotContains(response, "Doctor overview")
        self.assertNotContains(response, "Operations overview")

    def test_pharmacy_dashboard_role_scoping(self):
        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pharmacy overview")
        self.assertNotContains(response, "Reception overview")
        self.assertNotContains(response, "Doctor overview")

    def test_admin_dashboard_role_scoping(self):
        self.client.force_login(self.admin_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations overview")
        self.assertNotContains(response, 'href="/patients/"')

    def test_doctor_metrics_aggregate_accurately_and_scoped_to_assigned_doctor(self):
        other_doctor_user = User.objects.create_user("other_doc", password="pwd")
        other_doctor_user.groups.add(Group.objects.get(name="Doctor"))
        other_profile = StaffProfile.objects.create(
            user=other_doctor_user,
            employee_id="DOC002",
        )

        patient1 = Patient.objects.create(mrn="PAT001", full_name="Patient One")
        patient2 = Patient.objects.create(mrn="PAT002", full_name="Patient Two")
        visit_type = VisitType.objects.create(name="Standard OPD", code="OPD-STD")

        now = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(hour=10)),
            timezone.get_current_timezone(),
        )

        # Doctor 1: 1 checked in, 1 scheduled today
        Appointment.objects.create(
            patient=patient1,
            doctor=self.doctor_profile,
            visit_type=visit_type,
            scheduled_at=now,
            status=Appointment.Status.CHECKED_IN,
        )
        Appointment.objects.create(
            patient=patient2,
            doctor=self.doctor_profile,
            visit_type=visit_type,
            scheduled_at=now + timedelta(hours=1),
            status=Appointment.Status.SCHEDULED,
        )

        # Other Doctor: 2 checked in today
        Appointment.objects.create(
            patient=patient1,
            doctor=other_profile,
            visit_type=visit_type,
            scheduled_at=now,
            status=Appointment.Status.CHECKED_IN,
        )
        # The signed-in doctor's appointments outside today must not leak into
        # the dashboard's daily schedule aggregate.
        Appointment.objects.create(
            patient=patient1,
            doctor=self.doctor_profile,
            visit_type=visit_type,
            scheduled_at=now - timedelta(days=1),
            status=Appointment.Status.CHECKED_IN,
        )

        self.client.force_login(self.doctor_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        # doctor_today_appointments should be 2 for Doctor 1 (not 3)
        self.assertEqual(response.context["doctor_today_appointments"], 2)
        # doctor_waiting_patients should be 1 for Doctor 1 (not 2 or 3)
        self.assertEqual(response.context["doctor_waiting_patients"], 1)

    def test_doctor_context_excludes_other_role_sensitive_aggregates(self):
        self.client.force_login(self.doctor_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")

        self.assertNotIn("reception_today_collections", response.context)
        self.assertNotIn("admin_today_collections", response.context)
        self.assertNotIn("admin_today_refunds", response.context)
        self.assertNotIn("pharmacy_issued_prescriptions", response.context)

    def test_pharmacy_dashboard_does_not_link_to_patient_or_billing_workspaces(self):
        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")

        self.assertNotContains(response, 'href="/patients/"')
        self.assertNotContains(response, 'href="/patients/register/"')
        self.assertNotContains(response, 'href="/invoices/"')
        self.assertContains(response, 'href="/pharmacy/prescriptions/"')

    def test_doctor_without_staff_profile_renders_safely(self):
        doc_no_profile = User.objects.create_user("doc_noprof", password="pwd")
        doc_no_profile.groups.add(Group.objects.get(name="Doctor"))
        self.client.force_login(doc_no_profile)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["doctor_today_appointments"], 0)
        self.assertEqual(response.context["doctor_waiting_patients"], 0)

    def test_links_point_only_to_authorized_workspaces(self):
        self.client.force_login(self.doctor_user)
        response = self.client.get("/", HTTP_HOST="staff.hms.test")
        # Doctor has view_patient, view_appointment, view_admission, but not add_patient or view_invoice
        self.assertContains(response, 'href="/patients/"')
        self.assertContains(response, 'href="/appointments/"')
        self.assertContains(response, 'href="/ipd/admissions/"')
        self.assertNotContains(response, 'href="/patients/register/"')
        self.assertNotContains(response, 'href="/invoices/"')

        self.client.force_login(self.reception_user)
        response_rec = self.client.get("/", HTTP_HOST="staff.hms.test")
        self.assertContains(response_rec, 'href="/patients/register/"')
        self.assertContains(response_rec, 'href="/appointments/create/"')
        self.assertContains(response_rec, 'href="/invoices/"')

    def test_bounded_aggregate_queries(self):
        self.client.force_login(self.reception_user)
        with self.assertNumQueries(17):
            response = self.client.get("/", HTTP_HOST="staff.hms.test")
            self.assertEqual(response.status_code, 200)
