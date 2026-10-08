import datetime
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.models import Department, DoctorSchedule, StaffProfile
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
class DoctorScheduleManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_sched_user",
            email="admin_sched@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Department
        cls.dept = Department.objects.create(
            code="OPD_DEPT",
            name="General OPD Department",
            display_order=1,
            is_active=True,
        )

        # Doctor user & profile
        cls.doctor_user = User.objects.create_user(
            username="dr_singh",
            email="dr.singh@test.hms",
            password="DocPassword123!",
            first_name="Alok",
            last_name="Singh",
            is_staff=True,
        )
        doctor_group = Group.objects.get(name="Doctor")
        cls.doctor_user.groups.add(doctor_group)

        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-SINGH",
            department=cls.dept,
            job_title="Consultant Physician",
            is_public=True,
        )

    def test_create_recurring_schedule(self):
        """Admin can create a recurring weekly OPD session for a doctor."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/doctorschedule/add/"
        payload = {
            "doctor": str(self.doctor_profile.pk),
            "weekday": str(DoctorSchedule.Weekday.MONDAY),
            "start_time": "09:00:00",
            "end_time": "13:00:00",
            "opd_room": "Room 101",
            "slot_duration_minutes": "15",
            "max_patients": "16",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        sched = DoctorSchedule.objects.filter(doctor=self.doctor_profile, weekday=DoctorSchedule.Weekday.MONDAY).first()
        self.assertIsNotNone(sched)
        self.assertEqual(sched.start_time, datetime.time(9, 0))
        self.assertEqual(sched.end_time, datetime.time(13, 0))
        self.assertEqual(sched.opd_room, "Room 101")
        self.assertTrue(sched.is_active)

    def test_end_time_before_start_time_rejected(self):
        """Reject schedule where session end time is before or equal to start time."""
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/doctorschedule/add/"
        payload = {
            "doctor": str(self.doctor_profile.pk),
            "weekday": str(DoctorSchedule.Weekday.TUESDAY),
            "start_time": "14:00:00",
            "end_time": "12:00:00",  # invalid
            "slot_duration_minutes": "15",
            "max_patients": "10",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("end_time", form.errors)

    def test_overlapping_schedule_conflict_rejected(self):
        """Cannot create overlapping active sessions for the same doctor on the same weekday."""
        DoctorSchedule.objects.create(
            doctor=self.doctor_profile,
            weekday=DoctorSchedule.Weekday.WEDNESDAY,
            start_time="09:00:00",
            end_time="12:00:00",
            is_active=True,
        )

        self.client.force_login(self.admin_user)
        add_url = "/admin/core/doctorschedule/add/"
        # Overlapping: 11:00 to 14:00
        payload = {
            "doctor": str(self.doctor_profile.pk),
            "weekday": str(DoctorSchedule.Weekday.WEDNESDAY),
            "start_time": "11:00:00",
            "end_time": "14:00:00",
            "slot_duration_minutes": "15",
            "max_patients": "10",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertTrue(any("Schedule conflict" in err for err in form.non_field_errors()))

    def test_non_overlapping_schedule_on_same_day_allowed(self):
        """Doctor can have separate morning and evening clinics on the same day."""
        DoctorSchedule.objects.create(
            doctor=self.doctor_profile,
            weekday=DoctorSchedule.Weekday.THURSDAY,
            start_time="09:00:00",
            end_time="12:00:00",
            is_active=True,
        )
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/doctorschedule/add/"
        # Evening clinic: 16:00 to 19:00
        payload = {
            "doctor": str(self.doctor_profile.pk),
            "weekday": str(DoctorSchedule.Weekday.THURSDAY),
            "start_time": "16:00:00",
            "end_time": "19:00:00",
            "slot_duration_minutes": "15",
            "max_patients": "10",
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DoctorSchedule.objects.filter(doctor=self.doctor_profile, weekday=DoctorSchedule.Weekday.THURSDAY).count(),
            2,
        )

    def test_public_doctor_api_returns_available_schedules(self):
        """Public doctor endpoint returns active weekly schedules."""
        DoctorSchedule.objects.create(
            doctor=self.doctor_profile,
            weekday=DoctorSchedule.Weekday.FRIDAY,
            start_time="10:00:00",
            end_time="13:00:00",
            opd_room="Room 303",
            slot_duration_minutes=20,
            max_patients=9,
            is_active=True,
        )
        response = self.client.get("/api/v1/doctors/", HTTP_HOST="patient.hms.test")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        doc = next((d for d in data if d["id"] == self.doctor_profile.pk), None)
        self.assertIsNotNone(doc)
        schedules = doc.get("available_schedules", [])
        self.assertTrue(len(schedules) >= 1)
        fri_sched = next((s for s in schedules if s["weekday"] == DoctorSchedule.Weekday.FRIDAY), None)
        self.assertIsNotNone(fri_sched)
        self.assertEqual(fri_sched["weekday_name"], "Friday")
        self.assertEqual(fri_sched["start_time"], "10:00")
        self.assertEqual(fri_sched["end_time"], "13:00")
        self.assertEqual(fri_sched["opd_room"], "Room 303")

    def test_unauthorized_user_denied_schedule_admin(self):
        """Non-admin and patient portal users cannot access schedule admin."""
        patient_user = User.objects.create_user(username="pat_sched", password="PatPassword123!", is_staff=False)
        self.client.force_login(patient_user)
        response = self.client.get("/admin/core/doctorschedule/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)
