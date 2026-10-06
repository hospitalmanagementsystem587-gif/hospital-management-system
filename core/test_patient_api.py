from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase
from django.utils import timezone
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Department,
    Patient,
    PatientAccount,
    StaffProfile,
    VisitType,
    Appointment,
    AuditEvent,
)

User = get_user_model()


class PatientApiTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Doctor group
        self.doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        self.reception_group, _ = Group.objects.get_or_create(name="Reception")

        # Department
        self.dept = Department.objects.create(code="MED", name="General Medicine", is_active=True)
        self.inactive_dept = Department.objects.create(code="INACT", name="Inactive Dept", is_active=False)

        # Doctor user & profile
        self.doctor_user = User.objects.create_user(
            username="doctor1",
            password="DoctorPass123!",
            first_name="Ramesh",
            last_name="Gupta",
        )
        self.doctor_user.groups.add(self.doctor_group)
        self.doctor_profile = StaffProfile.objects.create(
            user=self.doctor_user,
            employee_id="DOC001",
            department=self.dept,
            job_title="Senior Consultant",
        )

        # Inactive Doctor user & profile
        self.inactive_doctor_user = User.objects.create_user(
            username="doctor_inact",
            password="DoctorPass123!",
            is_active=False,
        )
        self.inactive_doctor_user.groups.add(self.doctor_group)
        self.inactive_doctor_profile = StaffProfile.objects.create(
            user=self.inactive_doctor_user,
            employee_id="DOC002",
            department=self.dept,
        )

        # Visit types
        self.visit_type = VisitType.objects.create(code="ROUTINE", name="Routine Consultation", is_active=True)
        self.inactive_visit_type = VisitType.objects.create(code="OLD", name="Old Visit Type", is_active=False)

        # Patient 1
        self.patient1 = Patient.objects.create(
            mrn="MRN-001",
            full_name="Ananya Verma",
            phone="+919876543210",
            email="ananya@example.com",
        )
        self.patient1_user = User.objects.create_user(
            username="patient1",
            password="PatientPass123!",
        )
        self.patient1_account = PatientAccount.objects.create(
            user=self.patient1_user,
            patient=self.patient1,
            is_verified=True,
        )

        # Patient 2
        self.patient2 = Patient.objects.create(
            mrn="MRN-002",
            full_name="Vikram Singh",
            phone="+919876543211",
            email="vikram@example.com",
        )
        self.patient2_user = User.objects.create_user(
            username="patient2",
            password="PatientPass123!",
        )
        self.patient2_account = PatientAccount.objects.create(
            user=self.patient2_user,
            patient=self.patient2,
            is_verified=True,
        )

        # Staff non-patient user (Reception)
        self.staff_user = User.objects.create_user(
            username="reception1",
            password="StaffPass123!",
        )
        self.staff_user.groups.add(self.reception_group)
        self.staff_profile = StaffProfile.objects.create(
            user=self.staff_user,
            employee_id="REC001",
            department=self.dept,
        )

    def _auth(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return token

    def test_unauthenticated_requests_are_rejected(self):
        res = self.client.get("/api/v1/me/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res = self.client.get("/api/v1/appointments/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res = self.client.post("/api/v1/appointments/", {})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_staff_accounts_cannot_use_patient_endpoints(self):
        self._auth(self.staff_user)
        res = self.client.get("/api/v1/me/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.get("/api/v1/appointments/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_can_read_only_their_own_profile(self):
        self._auth(self.patient1_user)
        res = self.client.get("/api/v1/me/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["mrn"], "MRN-001")
        self.assertEqual(res.data["full_name"], "Ananya Verma")

    def test_doctors_and_visit_types_catalog(self):
        self._auth(self.patient1_user)
        res = self.client.get("/api/v1/doctors/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        doctor_ids = [d["id"] for d in res.data]
        self.assertIn(self.doctor_profile.id, doctor_ids)
        self.assertNotIn(self.inactive_doctor_profile.id, doctor_ids)

        res = self.client.get("/api/v1/visit-types/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        vt_ids = [v["id"] for v in res.data]
        self.assertIn(self.visit_type.id, vt_ids)
        self.assertNotIn(self.inactive_visit_type.id, vt_ids)

    def test_booking_succeeds_and_cannot_override_patient_identity(self):
        self._auth(self.patient1_user)
        slot_time = timezone.now() + timedelta(days=1, hours=2)

        # Attempt to inject patient2's id, fake MRN, and queue_number
        payload = {
            "doctor": self.doctor_profile.id,
            "visit_type": self.visit_type.id,
            "scheduled_at": slot_time.isoformat(),
            "patient": self.patient2.id,
            "patient_id": self.patient2.id,
            "mrn": "FAKE-MRN",
            "queue_number": 999,
            "status": "completed",
        }
        res = self.client.post("/api/v1/appointments/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        appt_id = res.data["id"]

        appt = Appointment.objects.get(id=appt_id)
        self.assertEqual(appt.patient, self.patient1)
        self.assertEqual(appt.status, Appointment.Status.SCHEDULED)
        self.assertNotEqual(appt.patient, self.patient2)

        # Check OPD slip fields returned
        self.assertEqual(res.data["patient_mrn"], "MRN-001")
        self.assertEqual(res.data["patient_name"], "Ananya Verma")

        # Check AuditEvent
        self.assertTrue(
            AuditEvent.objects.filter(
                target_id=str(appt_id), action="appointment.created"
            ).exists()
        )


    def test_slot_conflicts_exact_and_overlapping(self):
        self._auth(self.patient1_user)
        slot_time = timezone.now() + timedelta(days=2, hours=3)

        res = self.client.post(
            "/api/v1/appointments/",
            {
                "doctor": self.doctor_profile.id,
                "visit_type": self.visit_type.id,
                "scheduled_at": slot_time.isoformat(),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Patient 2 tries exact slot -> 409
        self._auth(self.patient2_user)
        res = self.client.post(
            "/api/v1/appointments/",
            {
                "doctor": self.doctor_profile.id,
                "visit_type": self.visit_type.id,
                "scheduled_at": slot_time.isoformat(),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

        # Patient 2 tries overlapping slot (e.g. +15 mins) -> 409
        overlap_time = slot_time + timedelta(minutes=15)
        res = self.client.post(
            "/api/v1/appointments/",
            {
                "doctor": self.doctor_profile.id,
                "visit_type": self.visit_type.id,
                "scheduled_at": overlap_time.isoformat(),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_cross_patient_access_and_not_found(self):
        # Patient 1 creates appointment
        slot_time = timezone.now() + timedelta(days=3)
        appt = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor_profile,
            visit_type=self.visit_type,
            scheduled_at=slot_time,
            status=Appointment.Status.SCHEDULED,
        )

        # Patient 2 authenticates
        self._auth(self.patient2_user)

        # Guessing another appointment ID returns 404 (doesn't leak existence)
        res = self.client.get(f"/api/v1/appointments/{appt.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Cannot cancel another patient's appointment
        res = self.client.post(f"/api/v1/appointments/{appt.id}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_appointment_cancellation(self):
        self._auth(self.patient1_user)
        slot_time = timezone.now() + timedelta(days=4)
        appt = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor_profile,
            visit_type=self.visit_type,
            scheduled_at=slot_time,
            status=Appointment.Status.SCHEDULED,
        )

        res = self.client.post(f"/api/v1/appointments/{appt.id}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "cancelled")

        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointment.Status.CANCELLED)
        self.assertIsNotNone(appt.cancelled_at)

        # Idempotent re-cancel returns 200
        res = self.client.post(f"/api/v1/appointments/{appt.id}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_cancellation_fails_for_in_progress_or_completed(self):
        self._auth(self.patient1_user)
        slot_time = timezone.now() + timedelta(days=5)
        appt = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor_profile,
            visit_type=self.visit_type,
            scheduled_at=slot_time,
            status=Appointment.Status.COMPLETED,
        )

        res = self.client.post(f"/api/v1/appointments/{appt.id}/cancel/")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_booking_inactive_doctor_is_rejected(self):
        self._auth(self.patient1_user)
        slot_time = timezone.now() + timedelta(days=6)
        res = self.client.post(
            "/api/v1/appointments/",
            {
                "doctor": self.inactive_doctor_profile.id,
                "visit_type": self.visit_type.id,
                "scheduled_at": slot_time.isoformat(),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_token_refresh_and_blacklisting_revocation(self):
        # Obtain token
        res = self.client.post(
            "/api/v1/auth/token/",
            {"username": self.patient1_user.username, "password": "PatientPass123!"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        access = res.data["access"]
        refresh = res.data["refresh"]

        # Refresh token works
        res_ref = self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh})
        self.assertEqual(res_ref.status_code, status.HTTP_200_OK)
        new_refresh = res_ref.data.get("refresh")

        # Because ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION are True,
        # old refresh token should now be blacklisted
        res_old = self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh})
        self.assertEqual(res_old.status_code, status.HTTP_401_UNAUTHORIZED)

        # Logout with new_refresh
        active_refresh = new_refresh or refresh
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res_ref.data['access']}")
        res_logout = self.client.post("/api/v1/auth/logout/", {"refresh": active_refresh})
        self.assertEqual(res_logout.status_code, status.HTTP_200_OK)

        # Active refresh is now blacklisted
        res_after_logout = self.client.post("/api/v1/auth/token/refresh/", {"refresh": active_refresh})
        self.assertEqual(res_after_logout.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_all_devices(self):
        res = self.client.post(
            "/api/v1/auth/token/",
            {"username": self.patient1_user.username, "password": "PatientPass123!"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        access = res.data["access"]
        refresh = res.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res_logout_all = self.client.post("/api/v1/auth/logout-all/")
        self.assertEqual(res_logout_all.status_code, status.HTTP_200_OK)

        # Attempt to refresh with refresh token -> should be rejected
        res_refresh = self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh})
        self.assertEqual(res_refresh.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_concurrent_booking_slot_conflict_prevention(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        import threading
        slot_time = timezone.now() + timedelta(days=7, hours=10)
        results = []

        def book(user):
            from django.db import connection
            client = APIClient()
            token = str(RefreshToken.for_user(user).access_token)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            res = client.post(
                "/api/v1/appointments/",
                {
                    "doctor": self.doctor_profile.id,
                    "visit_type": self.visit_type.id,
                    "scheduled_at": slot_time.isoformat(),
                },
                format="json",
            )
            results.append(res.status_code)
            connection.close()

        t1 = threading.Thread(target=book, args=(self.patient1_user,))
        t2 = threading.Thread(target=book, args=(self.patient2_user,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertIn(status.HTTP_201_CREATED, results)
        self.assertIn(status.HTTP_409_CONFLICT, results)
        self.assertEqual(len(results), 2)

    def test_auth_throttling_rejects_excessive_attempts(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(10):
            self.client.post(
                "/api/v1/auth/token/",
                {"username": "nonexistent", "password": "wrong"},
            )
        # The 11th attempt within 1 minute should be throttled (10/min)
        res = self.client.post(
            "/api/v1/auth/token/",
            {"username": "nonexistent", "password": "wrong"},
        )
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


