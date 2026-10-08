from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.test import TestCase, override_settings

from core.models import Department, DoctorSpecialty, Specialty, StaffProfile
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
class DoctorSpecialtyRelationshipsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_rel_user",
            email="admin_rel@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Department
        cls.dept = Department.objects.create(
            code="CARDIO_DEPT",
            name="Department of Cardiology",
            display_order=1,
            is_active=True,
        )

        # Doctor user & profile
        cls.doctor_user = User.objects.create_user(
            username="dr_verma",
            email="dr.verma@test.hms",
            password="DocPassword123!",
            first_name="Sunil",
            last_name="Verma",
            is_staff=True,
        )
        doctor_group = Group.objects.get(name="Doctor")
        cls.doctor_user.groups.add(doctor_group)

        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-VERMA",
            department=cls.dept,
            job_title="Interventional Cardiologist",
            qualifications="MBBS, MD, DM",
            is_public=True,
        )

        # Specialties
        cls.spec_cardio = Specialty.objects.create(
            code="INT_CARDIO",
            name="Interventional Cardiology",
            display_order=1,
            is_active=True,
        )
        cls.spec_electrophys = Specialty.objects.create(
            code="ELECTROPHYS",
            name="Cardiac Electrophysiology",
            display_order=2,
            is_active=True,
        )

    def test_assign_multiple_specialties_to_doctor(self):
        """Doctor can be assigned multiple specialties with one marked as primary."""
        rel1 = DoctorSpecialty.objects.create(
            doctor=self.doctor_profile,
            specialty=self.spec_cardio,
            is_primary=True,
        )
        rel2 = DoctorSpecialty.objects.create(
            doctor=self.doctor_profile,
            specialty=self.spec_electrophys,
            is_primary=False,
        )
        self.assertEqual(self.doctor_profile.specialties.count(), 2)
        self.assertTrue(rel1.is_primary)
        self.assertFalse(rel2.is_primary)

    def test_duplicate_specialty_assignment_prevented(self):
        """Cannot assign the same specialty twice to the same doctor (UniqueConstraint)."""
        DoctorSpecialty.objects.create(
            doctor=self.doctor_profile,
            specialty=self.spec_cardio,
            is_primary=True,
        )
        with self.assertRaises(IntegrityError):
            DoctorSpecialty.objects.create(
                doctor=self.doctor_profile,
                specialty=self.spec_cardio,
                is_primary=False,
            )

    def test_doctor_specialty_admin_access_and_inline(self):
        """Admin can view DoctorSpecialty in admin and manage via StaffProfile inline."""
        self.client.force_login(self.admin_user)
        # Check direct changelist
        response = self.client.get("/admin/core/doctorspecialty/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)

        # Check StaffProfile change page includes inline formset
        response = self.client.get(
            f"/admin/core/staffprofile/{self.doctor_profile.pk}/change/",
            HTTP_HOST="admin.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Doctor Specialties")

    def test_public_doctor_api_exposes_specialties_and_primary(self):
        """Public Doctor API returns assigned specialties and primary specialty details."""
        DoctorSpecialty.objects.create(
            doctor=self.doctor_profile,
            specialty=self.spec_cardio,
            is_primary=True,
        )
        DoctorSpecialty.objects.create(
            doctor=self.doctor_profile,
            specialty=self.spec_electrophys,
            is_primary=False,
        )

        response = self.client.get("/api/v1/doctors/", HTTP_HOST="patient.hms.test")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        doc_entry = next((d for d in data if d["id"] == self.doctor_profile.pk), None)
        self.assertIsNotNone(doc_entry)
        self.assertEqual(len(doc_entry["specialties"]), 2)
        self.assertEqual(doc_entry["primary_specialty"]["code"], "INT_CARDIO")

    def test_query_doctors_by_specialty(self):
        """Public Doctor API can filter doctors by specialty code or name."""
        DoctorSpecialty.objects.create(
            doctor=self.doctor_profile,
            specialty=self.spec_cardio,
            is_primary=True,
        )
        # Search by specialty code
        response = self.client.get("/api/v1/doctors/?specialty=INT_CARDIO", HTTP_HOST="patient.hms.test")
        self.assertEqual(response.status_code, 200)
        ids = [d["id"] for d in response.json()]
        self.assertIn(self.doctor_profile.pk, ids)

        # Search by unassigned specialty
        other_spec = Specialty.objects.create(code="DERMA", name="Dermatology")
        response = self.client.get("/api/v1/doctors/?specialty=DERMA", HTTP_HOST="patient.hms.test")
        self.assertEqual(response.status_code, 200)
        ids = [d["id"] for d in response.json()]
        self.assertNotIn(self.doctor_profile.pk, ids)

    def test_unauthorized_user_denied_relationship_admin(self):
        """Unauthorized non-staff or patient users cannot access DoctorSpecialty admin."""
        patient_user = User.objects.create_user(
            username="patient_rel",
            password="PatientPassword123!",
            is_staff=False,
        )
        self.client.force_login(patient_user)
        response = self.client.get("/admin/core/doctorspecialty/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)
