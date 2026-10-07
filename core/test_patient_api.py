from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase
from django.utils import timezone
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APIClient

from decimal import Decimal
from core.models import (
    Adjustment,
    Department,
    Invoice,
    InvoiceLine,
    Patient,
    PatientAccount,
    Payment,
    PaymentMethod,
    Refund,
    StaffProfile,
    VisitType,
    Appointment,
    AuditEvent,
    Bed,
    HealthPackage,
    HealthContent,
    Service,
    Ward,
)

User = get_user_model()


class PublicCapacityAndPackageApiTests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.ward = Ward.objects.create(code="ICU-A", name="ICU A", category=Ward.Category.ICU)
        Bed.objects.create(ward=self.ward, bed_number="1", status=Bed.Status.AVAILABLE)
        Bed.objects.create(ward=self.ward, bed_number="2", status=Bed.Status.OCCUPIED, notes="private")
        Bed.objects.create(ward=self.ward, bed_number="3", status=Bed.Status.MAINTENANCE)

    def test_bed_availability_is_aggregate_and_privacy_safe(self):
        response = self.client.get("/api/v1/bed-availability/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json()["categories"],
            [{
                "category": "icu", "label": "Intensive Care Unit (ICU)",
                "total": 3, "available": 1, "occupied": 1, "maintenance": 1,
            }],
        )
        payload = str(response.json()).lower()
        self.assertNotIn("bed_number", payload)
        self.assertNotIn("notes", payload)
        self.assertNotIn("patient", payload)
        self.assertIn("max-age=30", response["Cache-Control"])

    def test_only_current_published_packages_are_returned(self):
        service = Service.objects.create(code="CBC", name="Complete blood count", current_charge=500)
        visible = HealthPackage.objects.create(
            code="WELLNESS", name="Approved wellness", price=Decimal("999.00"),
            valid_from=date.today(), is_published=True,
        )
        visible.included_services.add(service)
        HealthPackage.objects.create(
            code="DRAFT", name="Draft package", price=Decimal("100.00"),
            valid_from=date.today(), is_published=False,
        )
        HealthPackage.objects.create(
            code="EXPIRED", name="Expired package", price=Decimal("100.00"),
            valid_from=date(2020, 1, 1), valid_until=date(2020, 1, 2), is_published=True,
        )

        response = self.client.get("/api/v1/health-packages/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["code"] for item in response.json()], ["WELLNESS"])
        self.assertEqual(response.json()[0]["price"], "999.00")
        self.assertEqual(response.json()[0]["included_services"], ["Complete blood count"])


class PublicHealthContentApiTests(TransactionTestCase):
    def test_only_reviewed_current_published_content_is_public(self):
        client = APIClient()
        author = User.objects.create_user("content-author")
        reviewer = User.objects.create_user("clinical-reviewer", first_name="Clinical", last_name="Reviewer")
        today = timezone.localdate()
        common = dict(category="Wellness", summary="Reviewed summary", body="Reviewed content.", author=author)
        HealthContent.objects.create(slug="visible", title="Visible", effective_from=today, status=HealthContent.Status.PUBLISHED, reviewer=reviewer, reviewed_at=timezone.now(), **common)
        HealthContent.objects.create(slug="draft", title="Draft", effective_from=today, status=HealthContent.Status.DRAFT, **common)
        HealthContent.objects.create(slug="expired", title="Expired", effective_from=today - timedelta(days=2), expires_on=today - timedelta(days=1), status=HealthContent.Status.PUBLISHED, reviewer=reviewer, reviewed_at=timezone.now(), **common)
        HealthContent.objects.create(slug="future", title="Future", effective_from=today + timedelta(days=1), status=HealthContent.Status.PUBLISHED, reviewer=reviewer, reviewed_at=timezone.now(), **common)
        HealthContent.objects.create(slug="superseded", title="Superseded", effective_from=today, status=HealthContent.Status.SUPERSEDED, reviewer=reviewer, reviewed_at=timezone.now(), **common)

        response = client.get("/api/v1/health-content/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["slug"] for item in response.json()], ["visible"])
        self.assertEqual(response.json()[0]["reviewer"], "Clinical Reviewer")
        self.assertIn("max-age=300", response["Cache-Control"])


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

        # NumberSequence for PATIENT MRN
        from core.models import NumberSequence
        NumberSequence.objects.get_or_create(code="PATIENT", defaults={"prefix": "P-", "next_value": 1})

    def _auth(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return token

    def test_public_opd_metrics_are_historical_aggregate_and_department_filtered(self):
        local_now = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
        scheduled = local_now - timedelta(days=7)
        for index in range(5):
            checked_in = scheduled + timedelta(minutes=index)
            Appointment.objects.create(
                patient=self.patient1, doctor=self.doctor_profile, visit_type=self.visit_type,
                scheduled_at=scheduled + timedelta(minutes=index),
                status=Appointment.Status.COMPLETED,
                checked_in_at=checked_in,
                started_at=checked_in + timedelta(minutes=10 + index),
                completed_at=checked_in + timedelta(minutes=30 + index),
            )

        response = self.client.get(
            "/api/v1/opd/historical-metrics/",
            {"weekday": scheduled.weekday(), "department": self.dept.code},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["kind"], "historical")
        self.assertFalse(response.json()["data_quality"]["forecast_available"])
        self.assertEqual(response.json()["hourly"][0]["sample_size"], 5)
        self.assertEqual(response.json()["hourly"][0]["average_wait_minutes"], 12)
        self.assertNotIn("patient", str(response.json()).lower())

        filtered = self.client.get(
            "/api/v1/opd/historical-metrics/",
            {"weekday": scheduled.weekday(), "department": "NOT-A-DEPARTMENT"},
        )
        self.assertEqual(filtered.json()["hourly"], [])


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
        concurrent_doc_user = User.objects.create_user(
            username="concurrent_doc",
            password="DoctorPass123!",
            first_name="Concurrent",
            last_name="Doctor",
            is_active=True,
        )
        concurrent_doc_user.groups.add(self.doctor_group)
        concurrent_doc = StaffProfile.objects.create(
            user=concurrent_doc_user,
            employee_id="DOC_CONCURRENT",
            department=self.dept,
            is_public=True,
        )
        slot_time = timezone.now() + timedelta(days=14, hours=10)
        results = []

        def book(user):
            from django.db import connection
            client = APIClient()
            token = str(RefreshToken.for_user(user).access_token)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            res = client.post(
                "/api/v1/appointments/",
                {
                    "doctor": concurrent_doc.id,
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

    def test_onboarding_request_otp_does_not_reveal_existence(self):
        # Request OTP for new phone
        res = self.client.post(
            "/api/v1/auth/otp/request/",
            {"contact": "+919999900001", "purpose": "registration"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("message", res.data)

        # Request OTP for existing phone
        res2 = self.client.post(
            "/api/v1/auth/otp/request/",
            {"contact": self.patient1.phone, "purpose": "registration"},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        # Uniform response prevents user enumeration
        self.assertEqual(res.data["message"], res2.data["message"])

    def test_onboarding_registration_flow(self):
        contact = "+919999911111"
        from core.services.verification import VerificationProvider
        _, code = VerificationProvider.create_challenge(
            contact=contact,
            purpose="registration",
            fixed_code="654321",
        )

        # Attempt with wrong code -> 400
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "contact": contact,
                "code": "000000",
                "full_name": "Dev Sharma",
                "password": "SecurePassword123!",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Attempt with valid code -> 201
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "contact": contact,
                "code": "654321",
                "full_name": "Dev Sharma",
                "password": "SecurePassword123!",
                "date_of_birth": "1995-05-15",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", res.data)
        self.assertIn("mrn", res.data["patient"])
        self.assertTrue(res.data["patient"]["mrn"].startswith("P-"))
        self.assertTrue(res.data["patient"]["phone_verified"])

        # Replay same code -> 400 (challenge marked as used)
        res_replay = self.client.post(
            "/api/v1/auth/register/",
            {
                "contact": contact,
                "code": "654321",
                "full_name": "Dev Sharma",
                "password": "SecurePassword123!",
            },
            format="json",
        )
        self.assertEqual(res_replay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_onboarding_claim_existing_patient_flow(self):
        # Create an unlinked existing patient registered at reception
        from core.services.numbering import next_number
        unlinked_patient = Patient.objects.create(
            mrn=next_number("PATIENT"),
            full_name="Sunita Mishra",
            phone="+919876549999",
        )

        from core.services.verification import VerificationProvider
        _, code = VerificationProvider.create_challenge(
            contact=unlinked_patient.phone,
            purpose="claim_patient",
            fixed_code="112233",
        )

        # Attempt to claim with wrong MRN -> 404
        res = self.client.post(
            "/api/v1/auth/claim-patient/",
            {
                "mrn": "MRN-NON-EXISTENT",
                "contact": unlinked_patient.phone,
                "code": "112233",
                "password": "SecurePassword123!",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Create challenge for the successful claim
        _, valid_code = VerificationProvider.create_challenge(
            contact=unlinked_patient.phone,
            purpose="claim_patient",
            fixed_code="445566",
        )

        # Claim with valid MRN and verified contact -> 200
        res = self.client.post(
            "/api/v1/auth/claim-patient/",
            {
                "mrn": unlinked_patient.mrn,
                "contact": unlinked_patient.phone,
                "code": "445566",
                "password": "SecurePassword123!",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)

        self.assertEqual(res.data["patient"]["mrn"], unlinked_patient.mrn)

        # Second attempt to claim same patient -> 409 Conflict
        _, code2 = VerificationProvider.create_challenge(
            contact=unlinked_patient.phone,
            purpose="claim_patient",
            fixed_code="998877",
        )
        res_dup = self.client.post(
            "/api/v1/auth/claim-patient/",
            {
                "mrn": unlinked_patient.mrn,
                "contact": unlinked_patient.phone,
                "code": "998877",
                "password": "SecurePassword123!",
            },
            format="json",
        )
        self.assertEqual(res_dup.status_code, status.HTTP_409_CONFLICT)

    def test_limited_patient_profile_update_and_audit(self):
        self._auth(self.patient1_user)

        # Attempt to modify restricted fields (mrn, allergy_safety_notes)
        patch_payload = {
            "mrn": "FORGED-MRN",
            "allergy_safety_notes": "Fake notes",
            "emergency_contact_name": "Father",
            "emergency_contact_phone": "+919876543299",
            "address": "New Flat 402, Gomti Nagar",
        }
        res = self.client.patch("/api/v1/me/", patch_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.patient1.refresh_from_db()
        # MRN and allergy notes remain untouched
        self.assertEqual(self.patient1.mrn, "MRN-001")
        self.assertNotEqual(self.patient1.allergy_safety_notes, "Fake notes")
        # Allowed fields are updated
        self.assertEqual(self.patient1.emergency_contact_name, "Father")
        self.assertEqual(self.patient1.address, "New Flat 402, Gomti Nagar")

        # AuditEvent is recorded
        self.assertTrue(
            AuditEvent.objects.filter(
                target_id=str(self.patient1.pk),
                action="patient.demographics_updated",
            ).exists()
        )

    def test_public_doctor_directory_and_detail(self):
        # AllowAny - no auth required
        res = self.client.get("/api/v1/doctors/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [d["id"] for d in res.data]
        self.assertIn(self.doctor_profile.id, ids)
        self.assertNotIn(self.inactive_doctor_profile.id, ids)

        # Non-public doctor should be excluded
        private_doc_user = User.objects.create_user(username="private_doc", password="Pass123!")
        private_doc_user.groups.add(self.doctor_group)
        private_doc = StaffProfile.objects.create(
            user=private_doc_user,
            employee_id="DOC_PRIV",
            department=self.dept,
            is_public=False,
        )
        res2 = self.client.get("/api/v1/doctors/")
        ids2 = [d["id"] for d in res2.data]
        self.assertNotIn(private_doc.id, ids2)

        # Doctor detail
        res_detail = self.client.get(f"/api/v1/doctors/{self.doctor_profile.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data["full_name"], "Ramesh Gupta")
        self.assertEqual(res_detail.data["department_name"], "General Medicine")

        # Inactive or non-public doctor detail returns 404
        res_inact = self.client.get(f"/api/v1/doctors/{self.inactive_doctor_profile.id}/")
        self.assertEqual(res_inact.status_code, status.HTTP_404_NOT_FOUND)

    def test_hospital_info_and_emergency_contacts(self):
        res = self.client.get("/api/v1/hospital-info/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("emergency_phone", res.data)
        self.assertIn("ambulance_phone", res.data)
        self.assertIn("address", res.data)
        self.assertEqual(res.data["emergency_phone"], "102")

    def test_hospital_departments_facilities_and_faqs(self):
        from core.models import HospitalFacility, HospitalFaq

        HospitalFacility.objects.create(
            title="24x7 ICU & Critical Care",
            category="Critical Care",
            description="Equipped with advanced multi-para monitors and ventilators.",
            highlight="24x7 Intensivist",
            display_order=1,
            is_active=True,
        )
        HospitalFacility.objects.create(
            title="Draft Facility",
            category="Draft",
            description="Not yet active",
            is_active=False,
        )

        HospitalFaq.objects.create(
            question="What are the visiting hours?",
            answer="Visiting hours are 4 PM to 7 PM daily.",
            category="Visiting Hours",
            highlight_tag="4 PM - 7 PM",
            display_order=1,
            is_active=True,
        )
        HospitalFaq.objects.create(
            question="Internal draft question?",
            answer="Secret internal answer",
            category="Internal",
            is_active=False,
        )

        # Departments
        res_dept = self.client.get("/api/v1/departments/")
        self.assertEqual(res_dept.status_code, status.HTTP_200_OK)
        dept_codes = [d["code"] for d in res_dept.data]
        self.assertIn("MED", dept_codes)
        self.assertNotIn("INACT", dept_codes)

        # Facilities
        res_fac = self.client.get("/api/v1/facilities/")
        self.assertEqual(res_fac.status_code, status.HTTP_200_OK)
        titles = [f["title"] for f in res_fac.data]
        self.assertIn("24x7 ICU & Critical Care", titles)
        self.assertNotIn("Draft Facility", titles)

        # FAQs
        res_faq = self.client.get("/api/v1/faqs/")
        self.assertEqual(res_faq.status_code, status.HTTP_200_OK)
        questions = [q["question"] for q in res_faq.data]
        self.assertIn("What are the visiting hours?", questions)
        self.assertNotIn("Internal draft question?", questions)

        # FAQ Search
        res_search = self.client.get("/api/v1/faqs/?search=visiting")
        self.assertEqual(res_search.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_search.data), 1)
        self.assertEqual(res_search.data[0]["question"], "What are the visiting hours?")

    def test_patient_billing_invoices_and_isolation(self):
        # Create payment method
        method = PaymentMethod.objects.create(name="Cash", is_active=True)

        # Create issued invoice for patient1
        inv1 = Invoice.objects.create(
            number="INV-2026-0001",
            patient=self.patient1,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("1500.00"),
            tax_total=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            total=Decimal("1500.00"),
            issued_at=timezone.now(),
        )
        line1 = InvoiceLine.objects.create(
            invoice=inv1,
            description="General OPD Consultation",
            quantity=1,
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00"),
        )
        line2 = InvoiceLine.objects.create(
            invoice=inv1,
            description="Complete Blood Count (CBC)",
            quantity=1,
            unit_price=Decimal("1000.00"),
            line_total=Decimal("1000.00"),
        )
        # Payment for inv1
        pay1 = Payment.objects.create(
            receipt_number="RCP-2026-0001",
            invoice=inv1,
            method=method,
            amount=Decimal("500.00"),
            reference="CASH-COUNTER-01",
            received_at=timezone.now(),
        )

        # Create draft invoice for patient1 (must be excluded from patient view)
        inv_draft = Invoice.objects.create(
            number="INV-2026-DRAFT",
            patient=self.patient1,
            status=Invoice.Status.DRAFT,
            subtotal=Decimal("200.00"),
            total=Decimal("200.00"),
        )

        # Create invoice for patient2 (must be isolated)
        inv2 = Invoice.objects.create(
            number="INV-2026-0002",
            patient=self.patient2,
            status=Invoice.Status.ISSUED,
            subtotal=Decimal("3000.00"),
            total=Decimal("3000.00"),
            issued_at=timezone.now(),
        )

        # Authenticate as patient1
        self._auth(self.patient1_user)

        # List invoices
        res = self.client.get("/api/v1/me/invoices/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        inv_numbers = [i["number"] for i in res.data]
        self.assertIn("INV-2026-0001", inv_numbers)
        self.assertNotIn("INV-2026-DRAFT", inv_numbers)
        self.assertNotIn("INV-2026-0002", inv_numbers)

        # Check decimal string serialization
        inv_data = res.data[0]
        self.assertEqual(inv_data["subtotal"], "1500.00")
        self.assertEqual(inv_data["total"], "1500.00")
        self.assertEqual(inv_data["paid_total"], "500.00")
        self.assertEqual(inv_data["outstanding_balance"], "1000.00")
        self.assertEqual(inv_data["currency"], "INR")
        self.assertFalse(inv_data["is_settled"])

        # Detail of owned invoice
        res_detail = self.client.get(f"/api/v1/me/invoices/{inv1.pk}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_detail.data["lines"]), 2)
        self.assertEqual(len(res_detail.data["payments"]), 1)
        self.assertEqual(res_detail.data["payments"][0]["receipt_number"], "RCP-2026-0001")
        self.assertEqual(res_detail.data["payments"][0]["amount"], "500.00")

        # Isolation test: accessing other patient's invoice returns 404
        res_other = self.client.get(f"/api/v1/me/invoices/{inv2.pk}/")
        self.assertEqual(res_other.status_code, status.HTTP_404_NOT_FOUND)

        # Isolation test: accessing draft invoice returns 404
        res_draft = self.client.get(f"/api/v1/me/invoices/{inv_draft.pk}/")
        self.assertEqual(res_draft.status_code, status.HTTP_404_NOT_FOUND)

        # Receipt detail of owned payment
        res_rcp = self.client.get("/api/v1/me/receipts/RCP-2026-0001/")
        self.assertEqual(res_rcp.status_code, status.HTTP_200_OK)
        self.assertEqual(res_rcp.data["receipt_number"], "RCP-2026-0001")
        self.assertEqual(res_rcp.data["amount"], "500.00")
        self.assertEqual(res_rcp.data["patient_mrn"], self.patient1.mrn)

        # Accessing non-existent or other patient receipt returns 404
        res_rcp_fake = self.client.get("/api/v1/me/receipts/RCP-NONEXISTENT/")
        self.assertEqual(res_rcp_fake.status_code, status.HTTP_404_NOT_FOUND)

        # Payment endpoint returns disabled 501
        res_pay = self.client.post(f"/api/v1/me/invoices/{inv1.pk}/pay/")
        self.assertEqual(res_pay.status_code, status.HTTP_501_NOT_IMPLEMENTED)
        self.assertFalse(res_pay.data["enabled"])
