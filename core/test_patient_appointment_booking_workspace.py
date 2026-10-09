from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    Department,
    DoctorSchedule,
    Patient,
    PatientAccount,
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
class PatientAppointmentBookingWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        configure_role_permissions()

        # Department
        cls.department = Department.objects.create(
            name="General Medicine",
            code="GENMED",
            is_active=True,
        )
        cls.inactive_dept = Department.objects.create(
            name="Inactive Specialization",
            code="INACT",
            is_active=False,
        )

        # Doctor 1 (Active)
        cls.doctor_user = User.objects.create_user(
            username="dr_alice",
            email="alice@example.com",
            password="password123",
            first_name="Alice",
            last_name="Doctor",
        )
        cls.doctor_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-ALICE-01",
            department=cls.department,
            consultation_fee=500,
        )

        # Doctor 2 (In inactive department)
        cls.doctor2_user = User.objects.create_user(
            username="dr_inactive",
            email="inactive@example.com",
            password="password123",
            first_name="Inactive",
            last_name="Doc",
        )
        cls.doctor2_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor_inactive_dept = StaffProfile.objects.create(
            user=cls.doctor2_user,
            employee_id="DOC-INACT-02",
            department=cls.inactive_dept,
            consultation_fee=500,
        )

        # Visit types
        cls.visit_type = VisitType.objects.create(
            name="Standard Consultation",
            code="STD-OPD",
            is_active=True,
        )
        cls.inactive_visit_type = VisitType.objects.create(
            name="Inactive Consultation",
            code="INACT-OPD",
            is_active=False,
        )

        # Patient 1 (Verified)
        cls.patient_user = User.objects.create_user(
            username="patient_jane",
            email="jane@example.com",
            password="password123",
            first_name="Jane",
            last_name="Doe",
        )
        cls.patient = Patient.objects.create(
            mrn="MRN-JANE-001",
            full_name="Jane Doe",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 30),
            phone="9876543210",
            email="jane@example.com",
        )
        cls.patient_account = PatientAccount.objects.create(
            user=cls.patient_user,
            patient=cls.patient,
            is_verified=True,
        )

        # Patient 2 (Other patient)
        cls.other_user = User.objects.create_user(
            username="patient_bob",
            email="bob@example.com",
            password="password123",
            first_name="Bob",
            last_name="Smith",
        )
        cls.other_patient = Patient.objects.create(
            mrn="MRN-BOB-002",
            full_name="Bob Smith",
            date_of_birth=timezone.localdate() - timedelta(days=365 * 40),
            phone="9876543211",
            email="bob@example.com",
        )
        cls.other_account = PatientAccount.objects.create(
            user=cls.other_user,
            patient=cls.other_patient,
            is_verified=True,
        )

        for weekday in range(7):
            DoctorSchedule.objects.create(
                doctor=cls.doctor,
                weekday=weekday,
                start_time="00:00",
                end_time="23:59",
                slot_duration_minutes=1,
                max_patients=1000,
                is_active=True,
            )

    def setUp(self):
        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_unauthenticated_booking_redirects_to_login(self):
        resp = self.client.get("/appointments/book/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_unverified_patient_cannot_access_booking(self):
        self.patient_account.is_verified = False
        self.patient_account.save()
        self.client.force_login(self.patient_user)
        resp = self.client.get("/appointments/book/")
        self.assertEqual(resp.status_code, 403)

    def test_archived_patient_cannot_access_booking(self):
        self.patient.archived_at = timezone.now()
        self.patient.save()
        self.client.force_login(self.patient_user)
        resp = self.client.get("/appointments/book/")
        self.assertEqual(resp.status_code, 403)

    def test_booking_page_renders_active_doctors_and_visit_types_only(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get("/appointments/book/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Alice Doctor")
        self.assertContains(resp, "DOC-ALICE-01")
        self.assertContains(resp, "Standard Consultation")
        # Inactive doctor / inactive visit type should not be available options
        self.assertNotContains(resp, "DOC-INACT-02")
        self.assertNotContains(resp, "Inactive Consultation")
        self.assertContains(resp, "₹500.00")

    def test_successful_appointment_booking(self):
        self.client.force_login(self.patient_user)
        future_time = timezone.now() + timedelta(days=3, hours=2)
        resp = self.client.post(
            "/appointments/book/",
            {
                "doctor": self.doctor.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": future_time.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/")

        # Verify created appointment is strictly tied to Jane Doe and has SCHEDULED status
        appt = Appointment.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.doctor, self.doctor)
        self.assertEqual(appt.visit_type, self.visit_type)
        self.assertEqual(appt.status, Appointment.Status.SCHEDULED)
        # Ensure Bob has no appointments created
        self.assertFalse(Appointment.objects.filter(patient=self.other_patient).exists())

    def test_cannot_book_appointment_for_another_patient(self):
        # Patient Jane submits a post trying to sneak in Bob's patient ID
        self.client.force_login(self.patient_user)
        future_time = timezone.now() + timedelta(days=4)
        resp = self.client.post(
            "/appointments/book/",
            {
                "patient": self.other_patient.pk,  # Malicious attempt
                "doctor": self.doctor.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": future_time.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(resp.status_code, 302)
        # The appointment was created, but MUST be assigned to Jane Doe, not Bob
        self.assertFalse(Appointment.objects.filter(patient=self.other_patient).exists())
        self.assertTrue(Appointment.objects.filter(patient=self.patient).exists())

    def test_cannot_book_in_the_past(self):
        self.client.force_login(self.patient_user)
        past_time = timezone.now() - timedelta(days=1)
        resp = self.client.post(
            "/appointments/book/",
            {
                "doctor": self.doctor.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": past_time.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Appointment time must be in the future.")
        self.assertFalse(Appointment.objects.filter(patient=self.patient).exists())

    def test_cannot_book_overlapping_conflicting_slot(self):
        # Create an existing active appointment for Dr. Alice
        existing_time = timezone.localtime(timezone.now() + timedelta(days=2, hours=4))
        Appointment.objects.create(
            patient=self.other_patient,
            doctor=self.doctor,
            visit_type=self.visit_type,
            scheduled_at=existing_time,
            status=Appointment.Status.SCHEDULED,
        )

        self.client.force_login(self.patient_user)
        # Attempt to book only 10 minutes after existing_time (within 30-min window)
        conflicting_time = existing_time + timedelta(minutes=10)
        resp = self.client.post(
            "/appointments/book/",
            {
                "doctor": self.doctor.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": conflicting_time.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "overlapping active appointment")
        self.assertFalse(Appointment.objects.filter(patient=self.patient).exists())

    def test_cannot_book_outside_published_doctor_schedule(self):
        self.doctor.schedules.all().delete()
        self.client.force_login(self.patient_user)
        future_time = timezone.now() + timedelta(days=5)
        response = self.client.post(
            "/appointments/book/",
            {
                "doctor": self.doctor.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": future_time.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "published schedule")
        self.assertFalse(Appointment.objects.filter(patient=self.patient).exists())

    def test_patient_can_cancel_only_own_scheduled_appointment(self):
        own = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            visit_type=self.visit_type,
            scheduled_at=timezone.now() + timedelta(days=6),
            status=Appointment.Status.SCHEDULED,
        )
        other = Appointment.objects.create(
            patient=self.other_patient,
            doctor=self.doctor,
            visit_type=self.visit_type,
            scheduled_at=timezone.now() + timedelta(days=7),
            status=Appointment.Status.SCHEDULED,
        )
        self.client.force_login(self.patient_user)
        self.assertEqual(
            self.client.post(f"/appointments/{other.pk}/cancel/").status_code,
            404,
        )
        response = self.client.post(f"/appointments/{own.pk}/cancel/")
        self.assertEqual(response.status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.status, Appointment.Status.CANCELLED)
        self.assertIsNotNone(own.cancelled_at)

    def test_fully_booked_schedule_is_rejected(self):
        future_time = timezone.localtime(timezone.now() + timedelta(days=8)).replace(
            second=0, microsecond=0
        )
        schedule = self.doctor.schedules.get(weekday=future_time.weekday())
        schedule.max_patients = 1
        schedule.save(update_fields=("max_patients", "updated_at"))
        Appointment.objects.create(
            patient=self.other_patient,
            doctor=self.doctor,
            visit_type=self.visit_type,
            scheduled_at=future_time.replace(hour=0, minute=0),
            status=Appointment.Status.SCHEDULED,
        )
        self.client.force_login(self.patient_user)
        response = self.client.post(
            "/appointments/book/",
            {
                "doctor": self.doctor.pk,
                "visit_type": self.visit_type.pk,
                "scheduled_at": future_time.replace(hour=12, minute=0).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fully booked")
