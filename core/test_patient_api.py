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

        # NumberSequence for PATIENT MRN
        from core.models import NumberSequence
        NumberSequence.objects.get_or_create(code="PATIENT", defaults={"prefix": "P-", "next_value": 1})

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

    def test_patient_medication_schedules_and_adherence(self):
        import uuid
        from datetime import date, timedelta
        from core.models import MedicationSchedule, MedicationDoseLog, Medicine, Prescription, PrescriptionItem

        self._auth(self.patient1_user)

        med1 = Medicine.objects.create(
            generic_name="Paracetamol",
            brand_name="Crocin 500",
            strength="500mg",
            dosage_form="Tablet",
            unit="strip",
        )

        rx1 = Prescription.objects.create(
            number="RX-2026-0001",
            patient=self.patient1,
            doctor=self.doctor_profile,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )

        rx1_item = PrescriptionItem.objects.create(
            prescription=rx1,
            medicine=med1,
            dosage="1 tablet",
            frequency="twice daily",
            duration="10 days",
            instructions="After meals",
            quantity=20,
        )

        # Create medication schedule for patient 1
        sched1 = MedicationSchedule.objects.create(
            prescription_item=rx1_item,
            patient=self.patient1,
            dose_amount="1 tablet",
            dose_unit="tablet",
            target_times=["08:00", "20:00"],
            meal_relation=MedicationSchedule.MealRelation.AFTER_MEAL,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=10),
            timezone="Asia/Kolkata",
            is_active=True,
            confirmed_by=self.doctor_profile,
        )

        # Inactive schedule should not be returned in list
        sched_inactive = MedicationSchedule.objects.create(
            prescription_item=rx1_item,
            patient=self.patient1,
            dose_amount="1 tablet",
            dose_unit="tablet",
            target_times=["14:00"],
            meal_relation=MedicationSchedule.MealRelation.BEFORE_MEAL,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=5),
            timezone="Asia/Kolkata",
            is_active=False,
            confirmed_by=self.doctor_profile,
        )


        # 1. List active schedules for patient 1
        res = self.client.get("/api/v1/me/medication-schedules/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [s["id"] for s in res.data]
        self.assertIn(sched1.id, ids)
        self.assertNotIn(sched_inactive.id, ids)
        self.assertEqual(res.data[0]["dose_amount"], "1 tablet")
        self.assertEqual(res.data[0]["target_times"], ["08:00", "20:00"])
        self.assertEqual(res.data[0]["meal_relation"], "after_meal")
        expected_doctor_name = self.doctor_user.get_full_name() or self.doctor_user.username
        self.assertEqual(res.data[0]["confirmed_by_name"], expected_doctor_name)


        # 2. Detail schedule
        res_detail = self.client.get(f"/api/v1/me/medication-schedules/{sched1.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data["id"], sched1.id)

        # 3. Cross-patient isolation: Patient 2 cannot access Patient 1's schedule
        self._auth(self.patient2_user)
        res_p2 = self.client.get(f"/api/v1/me/medication-schedules/{sched1.id}/")
        self.assertEqual(res_p2.status_code, status.HTTP_404_NOT_FOUND)

        # 4. Log dose event (Patient 1)
        self._auth(self.patient1_user)
        key1 = uuid.uuid4()
        scheduled_slot = "2026-10-07T08:00:00Z"
        logged_at = "2026-10-07T08:05:00Z"

        res_log = self.client.post(
            "/api/v1/me/medication-schedules/log-dose/",
            {
                "schedule": sched1.id,
                "scheduled_time": scheduled_slot,
                "action": "taken",
                "logged_at": logged_at,
                "idempotency_key": str(key1),
            },
            format="json",
        )
        self.assertEqual(res_log.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_log.data["action"], "taken")

        # 5. Idempotent re-send with same idempotency key returns HTTP 200 OK
        res_log_dup = self.client.post(
            "/api/v1/me/medication-schedules/log-dose/",
            {
                "schedule": sched1.id,
                "scheduled_time": scheduled_slot,
                "action": "taken",
                "logged_at": logged_at,
                "idempotency_key": str(key1),
            },
            format="json",
        )
        self.assertEqual(res_log_dup.status_code, status.HTTP_200_OK)

        # 6. Prescription cancellation hides schedule
        rx1.status = Prescription.Status.CANCELLED
        rx1.save()


        res_after_cancel = self.client.get("/api/v1/me/medication-schedules/")
        self.assertEqual(res_after_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_after_cancel.data), 0)

        res_detail_cancel = self.client.get(f"/api/v1/me/medication-schedules/{sched1.id}/")
        self.assertEqual(res_detail_cancel.status_code, status.HTTP_404_NOT_FOUND)


