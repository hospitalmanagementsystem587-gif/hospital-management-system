from datetime import time, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Department,
    DoctorSchedule,
    DoctorSpecialty,
    Patient,
    PatientAccount,
    Specialty,
    StaffProfile,
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
class PatientDoctorDirectoryWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        configure_role_permissions()

        # Departments
        cls.dept_cardio = Department.objects.create(
            name="Cardiology",
            code="CARDIO",
            is_active=True,
        )
        cls.dept_neuro = Department.objects.create(
            name="Neurology",
            code="NEURO",
            is_active=True,
        )
        cls.dept_inactive = Department.objects.create(
            name="Decommissioned Dept",
            code="DECOMM",
            is_active=False,
        )

        # Specialties
        cls.spec_cardio = Specialty.objects.create(
            name="Interventional Cardiology",
            code="INT_CARDIO",
            is_active=True,
        )
        cls.spec_neuro = Specialty.objects.create(
            name="Stroke Specialist",
            code="STROKE",
            is_active=True,
        )

        # Doctor 1: Active, public, full profile
        cls.doc1_user = User.objects.create_user(
            username="dr_sharma",
            email="sharma@hospital.test",
            password="password123",
            first_name="Rajesh",
            last_name="Sharma",
        )
        cls.doc1_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc1_profile = StaffProfile.objects.create(
            user=cls.doc1_user,
            employee_id="DOC-SHARMA",
            department=cls.dept_cardio,
            job_title="Senior Consultant Cardiologist",
            qualifications="MBBS, MD, DM",
            experience_years=15,
            languages="Hindi, English",
            opd_room="Room 101",
            consultation_fee=800,
            biography="Expert in interventional cardiology and cardiac care.",
            is_public=True,
        )
        DoctorSpecialty.objects.create(
            doctor=cls.doc1_profile,
            specialty=cls.spec_cardio,
            is_primary=True,
        )
        DoctorSchedule.objects.create(
            doctor=cls.doc1_profile,
            weekday=DoctorSchedule.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(13, 0),
            opd_room="Room 101",
            is_active=True,
        )

        # Doctor 2: Active, public, neurology
        cls.doc2_user = User.objects.create_user(
            username="dr_verma",
            email="verma@hospital.test",
            password="password123",
            first_name="Pooja",
            last_name="Verma",
        )
        cls.doc2_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc2_profile = StaffProfile.objects.create(
            user=cls.doc2_user,
            employee_id="DOC-VERMA",
            department=cls.dept_neuro,
            job_title="Chief Neurosurgeon",
            qualifications="MBBS, MS, MCh",
            experience_years=12,
            languages="English",
            opd_room="Room 202",
            consultation_fee=1000,
            biography="Specialist in neuro-vascular interventions.",
            is_public=True,
        )
        DoctorSpecialty.objects.create(
            doctor=cls.doc2_profile,
            specialty=cls.spec_neuro,
            is_primary=True,
        )

        # Doctor 3: Non-public (is_public=False)
        cls.doc3_user = User.objects.create_user(
            username="dr_private",
            email="private@hospital.test",
            password="password123",
            first_name="Secret",
            last_name="Doctor",
        )
        cls.doc3_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc3_profile = StaffProfile.objects.create(
            user=cls.doc3_user,
            employee_id="DOC-PRIV",
            department=cls.dept_cardio,
            consultation_fee=900,
            is_public=False,
        )

        # Doctor 4: Inactive department
        cls.doc4_user = User.objects.create_user(
            username="dr_inactivedept",
            email="inactivedept@hospital.test",
            password="password123",
            first_name="InactiveDept",
            last_name="Doctor",
        )
        cls.doc4_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc4_profile = StaffProfile.objects.create(
            user=cls.doc4_user,
            employee_id="DOC-INACTDEPT",
            department=cls.dept_inactive,
            consultation_fee=500,
            is_public=True,
        )

        # Doctor 5: Inactive user
        cls.doc5_user = User.objects.create_user(
            username="dr_inactiveuser",
            email="inactiveuser@hospital.test",
            password="password123",
            first_name="InactiveUser",
            last_name="Doctor",
            is_active=False,
        )
        cls.doc5_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc5_profile = StaffProfile.objects.create(
            user=cls.doc5_user,
            employee_id="DOC-INACTUSER",
            department=cls.dept_cardio,
            consultation_fee=500,
            is_public=True,
        )

        # Verified Patient
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

    def setUp(self):
        self.client = Client(HTTP_HOST="patient.hms.test")

    def test_unauthenticated_directory_redirects_to_login(self):
        resp = self.client.get("/doctors/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_unverified_patient_cannot_access_directory(self):
        self.patient_account.is_verified = False
        self.patient_account.save()
        self.client.force_login(self.patient_user)
        resp = self.client.get("/doctors/")
        self.assertEqual(resp.status_code, 403)

    def test_archived_patient_cannot_access_directory(self):
        self.patient.archived_at = timezone.now()
        self.patient.save()
        self.client.force_login(self.patient_user)
        resp = self.client.get("/doctors/")
        self.assertEqual(resp.status_code, 403)

    def test_directory_renders_public_active_doctors_only(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get("/doctors/")
        self.assertEqual(resp.status_code, 200)

        # Public active doctors present
        self.assertContains(resp, "Dr. Rajesh Sharma")
        self.assertContains(resp, "Dr. Pooja Verma")
        self.assertContains(resp, "Cardiology")
        self.assertContains(resp, "Neurology")
        self.assertContains(resp, "₹800")
        self.assertContains(resp, "₹1000")
        self.assertContains(resp, "Room 101")
        self.assertContains(resp, "Monday")

        # Excluded doctors must NOT appear
        self.assertNotContains(resp, "Secret Doctor")
        self.assertNotContains(resp, "InactiveDept Doctor")
        self.assertNotContains(resp, "InactiveUser Doctor")

        # Private internal fields must NOT leak
        self.assertNotContains(resp, "dr_sharma")
        self.assertNotContains(resp, "DOC-SHARMA")
        self.assertNotContains(resp, "sharma@hospital.test")

    def test_directory_filter_by_department(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get("/doctors/?department=CARDIO")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dr. Rajesh Sharma")
        self.assertNotContains(resp, "Dr. Pooja Verma")

    def test_directory_filter_by_specialty(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get("/doctors/?specialty=STROKE")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dr. Pooja Verma")
        self.assertNotContains(resp, "Dr. Rajesh Sharma")

    def test_directory_search_query(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get("/doctors/?q=interventional")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dr. Rajesh Sharma")
        self.assertNotContains(resp, "Dr. Pooja Verma")

    def test_directory_search_empty_state(self):
        self.client.force_login(self.patient_user)
        resp = self.client.get("/doctors/?q=NonExistentSpecialist")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No matching doctors found in the directory.")
