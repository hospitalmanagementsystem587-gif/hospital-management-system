from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    AuditEvent,
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
class AppointmentWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Doctor 1
        cls.doctor_user = User.objects.create_user("doctor_user", password="password")
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC001",
            consultation_fee=500,
        )

        # Doctor 2
        cls.doctor2_user = User.objects.create_user("doctor2_user", password="password")
        cls.doctor2_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor2_profile = StaffProfile.objects.create(
            user=cls.doctor2_user,
            employee_id="DOC002",
            consultation_fee=750,
        )

        # Reception
        cls.reception_user = User.objects.create_user("reception_user", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC001",
        )

        # Administrator
        cls.admin_user = User.objects.create_user("admin_user", password="password", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM001",
        )

        # Ordinary non-staff user
        cls.ordinary_user = User.objects.create_user("ordinary_user", password="password")

        # Pharmacy user (no appointment view permission)
        cls.pharmacy_user = User.objects.create_user("pharmacy_user", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM001",
        )

        cls.patient1 = Patient.objects.create(mrn="MRN-001", full_name="Alice Patient")
        cls.patient2 = Patient.objects.create(mrn="MRN-002", full_name="Bob Patient")
        cls.visit_type = VisitType.objects.create(name="Standard Consultation", code="STD-OPD")

        local_today = timezone.localdate()
        cls.now = timezone.make_aware(
            datetime.combine(local_today, time(hour=10)),
            timezone.get_current_timezone(),
        )

        # Existing appointment for Doctor 1
        cls.appt_doc1 = Appointment.objects.create(
            patient=cls.patient1,
            doctor=cls.doctor_profile,
            visit_type=cls.visit_type,
            scheduled_at=cls.now,
            status=Appointment.Status.SCHEDULED,
        )

        # Existing appointment for Doctor 2
        cls.appt_doc2 = Appointment.objects.create(
            patient=cls.patient2,
            doctor=cls.doctor2_profile,
            visit_type=cls.visit_type,
            scheduled_at=cls.now + timedelta(hours=1),
            status=Appointment.Status.SCHEDULED,
        )

    def test_anonymous_redirects_to_login(self):
        response = self.client.get("/appointments/", HTTP_HOST="staff.hms.test")
        self.assertRedirects(response, "/accounts/login/?next=/appointments/", fetch_redirect_response=False)

    def test_unauthorized_roles_denied(self):
        self.client.force_login(self.ordinary_user)
        response = self.client.get("/appointments/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.pharmacy_user)
        response_pharm = self.client.get("/appointments/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response_pharm.status_code, 403)

    def test_doctor_scoping_sees_only_own_appointments(self):
        self.client.force_login(self.doctor_user)
        day_str = timezone.localtime(self.now).strftime("%Y-%m-%d")
        response = self.client.get(
            f"/appointments/?date={day_str}",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Patient")
        self.assertNotContains(response, "Bob Patient")

    def test_reception_sees_all_appointments_and_admin_is_denied(self):
        day_str = timezone.localtime(self.now).strftime("%Y-%m-%d")
        self.client.force_login(self.reception_user)
        response = self.client.get(
            f"/appointments/?date={day_str}",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Patient")
        self.assertContains(response, "Bob Patient")

        self.client.force_login(self.admin_user)
        self.assertEqual(
            self.client.get(
                f"/appointments/?date={day_str}", HTTP_HOST="staff.hms.test"
            ).status_code,
            403,
        )

    def test_reception_books_appointment_with_validation_and_audit(self):
        self.client.force_login(self.reception_user)
        target_dt = self.now + timedelta(hours=3)
        schedule_time = timezone.localtime(target_dt).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            "/appointments/create/",
            {
                "patient": self.patient2.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": schedule_time,
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        new_appt = Appointment.objects.get(
            patient=self.patient2,
            doctor=self.doctor_profile,
            scheduled_at=target_dt,
        )
        self.assertEqual(new_appt.status, Appointment.Status.SCHEDULED)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="appointment.created",
                target_id=str(new_appt.pk),
            ).exists()
        )

    def test_slot_conflict_prevention_on_create(self):
        self.client.force_login(self.reception_user)
        # Attempt to book at same time as appt_doc1 (using local time string as browser submits)
        local_time_str = timezone.localtime(self.appt_doc1.scheduled_at).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            "/appointments/create/",
            {
                "patient": self.patient2.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": local_time_str,
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This doctor already has an overlapping active appointment.")

    def test_slot_conflict_prevention_on_reschedule(self):
        self.client.force_login(self.reception_user)
        # Attempt to reschedule appt_doc2 to appt_doc1 doctor and slot
        local_time_str = timezone.localtime(self.appt_doc1.scheduled_at).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            f"/appointments/{self.appt_doc2.pk}/reschedule/",
            {
                "patient": self.patient2.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": local_time_str,
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This doctor already has an overlapping active appointment.")

    def test_doctor_cannot_create_or_reschedule_appointments(self):
        self.client.force_login(self.doctor_user)
        schedule_time = (self.now + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")
        res_create = self.client.post(
            "/appointments/create/",
            {
                "patient": self.patient1.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": schedule_time,
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_create.status_code, 403)

        res_reschedule = self.client.post(
            f"/appointments/{self.appt_doc1.pk}/reschedule/",
            {
                "patient": self.patient1.pk,
                "doctor": self.doctor_profile.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": schedule_time,
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_reschedule.status_code, 403)

    def test_status_transitions_by_reception_and_doctor(self):
        # 1. Reception checks in
        self.client.force_login(self.reception_user)
        res_checkin = self.client.post(
            f"/appointments/{self.appt_doc1.pk}/transition/",
            {"action": "check_in"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_checkin.status_code, 302)
        self.appt_doc1.refresh_from_db()
        self.assertEqual(self.appt_doc1.status, Appointment.Status.CHECKED_IN)
        self.assertIsNotNone(self.appt_doc1.checked_in_at)

        # 2. Reception cannot perform doctor action "start"
        res_invalid = self.client.post(
            f"/appointments/{self.appt_doc1.pk}/transition/",
            {"action": "start"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_invalid.status_code, 400)

        # 3. Doctor starts consultation
        self.client.force_login(self.doctor_user)
        res_start = self.client.post(
            f"/appointments/{self.appt_doc1.pk}/transition/",
            {"action": "start"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_start.status_code, 302)
        self.appt_doc1.refresh_from_db()
        self.assertEqual(self.appt_doc1.status, Appointment.Status.IN_PROGRESS)
        self.assertIsNotNone(self.appt_doc1.started_at)

        # 4. Doctor completes consultation
        res_complete = self.client.post(
            f"/appointments/{self.appt_doc1.pk}/transition/",
            {"action": "complete"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_complete.status_code, 302)
        self.appt_doc1.refresh_from_db()
        self.assertEqual(self.appt_doc1.status, Appointment.Status.COMPLETED)
        self.assertIsNotNone(self.appt_doc1.completed_at)

    def test_doctor_cannot_transition_other_doctors_appointments(self):
        # Doctor 1 cannot transition Doctor 2's appointment
        self.client.force_login(self.doctor_user)
        res = self.client.post(
            f"/appointments/{self.appt_doc2.pk}/transition/",
            {"action": "check_in"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res.status_code, 404)

    def test_consultation_price_displayed_in_workspace(self):
        self.client.force_login(self.reception_user)
        day_str = timezone.localtime(self.now).strftime("%Y-%m-%d")
        response = self.client.get(
            f"/appointments/?date={day_str}",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹500")
        self.assertContains(response, "₹750")
