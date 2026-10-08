import html
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from core.models import Appointment, Department, StaffProfile
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
class DoctorManagementCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_doctor_cms",
            email="admin_doc@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Department
        cls.dept = Department.objects.create(
            code="CARDIO",
            name="Cardiology",
            description="Heart and vascular care",
            display_order=1,
            is_active=True,
        )

        # Doctor user and profile
        cls.doctor_user = User.objects.create_user(
            username="dr_sharma",
            email="dr.sharma@test.hms",
            password="DocPassword123!",
            first_name="Rajesh",
            last_name="Sharma",
            is_staff=True,
        )
        doctor_group = Group.objects.get(name="Doctor")
        cls.doctor_user.groups.add(doctor_group)

        cls.doctor_profile = StaffProfile.objects.create(
            user=cls.doctor_user,
            employee_id="DOC-001",
            department=cls.dept,
            job_title="Senior Consultant Cardiologist",
            qualifications="MBBS, MD (Med), DM (Cardio)",
            experience_years=15,
            languages="Hindi, English",
            opd_room="Room 201",
            opd_schedule="Mon-Fri: 10 AM - 2 PM",
            consultation_fee=800,
            biography="Dr. Rajesh Sharma is a leading interventional cardiologist.",
            is_public=True,
        )

        # Patient user for unauthorized test
        cls.patient_user = User.objects.create_user(
            username="patient_test_user",
            password="PatientPassword123!",
            is_staff=False,
        )
        patient_group, _ = Group.objects.get_or_create(name="Patient")
        cls.patient_user.groups.add(patient_group)

    def test_authorized_admin_can_view_staff_changelist(self):
        """Admin can view the staff and doctor management changelist."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/staffprofile/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DOC-001")
        self.assertContains(response, "Rajesh Sharma")
        self.assertContains(response, "Cardiology")

    def test_authorized_admin_can_edit_doctor_profile(self):
        """Admin can edit qualifications, experience, schedule, and public visibility."""
        self.client.force_login(self.admin_user)
        change_url = f"/admin/core/staffprofile/{self.doctor_profile.pk}/change/"
        payload = {
            "user": str(self.doctor_user.pk),
            "employee_id": "DOC-001",
            "department": str(self.dept.pk),
            "job_title": "Chief of Cardiology",
            "qualifications": "MBBS, MD, DM, FACC",
            "experience_years": "18",
            "languages": "Hindi, English, Punjabi",
            "opd_room": "Room 205",
            "opd_schedule": "Mon-Sat: 9 AM - 1 PM",
            "consultation_fee": "1000",
            "biography": "Chief cardiologist with over 18 years of clinical experience.",
            "is_public": "on",
            "doctor_specialties-TOTAL_FORMS": "0",
            "doctor_specialties-INITIAL_FORMS": "0",
            "doctor_specialties-MIN_NUM_FORMS": "0",
            "doctor_specialties-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        response = self.client.post(change_url, data=payload, follow=True, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.doctor_profile.refresh_from_db()
        self.assertEqual(self.doctor_profile.job_title, "Chief of Cardiology")
        self.assertEqual(self.doctor_profile.experience_years, 18)
        self.assertEqual(self.doctor_profile.consultation_fee, 1000)
        self.assertTrue(self.doctor_profile.is_public)

    def test_duplicate_employee_id_prevented(self):
        """Cannot assign an existing employee ID to another staff profile."""
        other_user = User.objects.create_user(
            username="other_staff",
            email="other@test.hms",
            password="OtherPassword123!",
            is_staff=True,
        )
        self.client.force_login(self.admin_user)
        add_url = "/admin/core/staffprofile/add/"
        payload = {
            "user": str(other_user.pk),
            "employee_id": "doc-001",  # Duplicate in lowercase
            "department": str(self.dept.pk),
            "job_title": "Junior Resident",
            "_save": "Save",
        }
        response = self.client.post(add_url, data=payload, HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIn("employee_id", form.errors)
        self.assertIn("Staff profile with Employee ID 'DOC-001' already exists.", form.errors["employee_id"])

    def test_public_visibility_toggle_hides_from_public_doctor_directory(self):
        """Toggling is_public to False hides doctor from public API without deleting profile or breaking records."""
        self.doctor_profile.is_public = False
        self.doctor_profile.save(update_fields=["is_public", "updated_at"])

        # Check directory API
        response = self.client.get("/api/v1/doctors/", HTTP_HOST="patient.hms.test")
        self.assertEqual(response.status_code, 200)
        ids = [doc["id"] for doc in response.json()]
        self.assertNotIn(self.doctor_profile.pk, ids)

        # Restore public visibility
        self.doctor_profile.is_public = True
        self.doctor_profile.save(update_fields=["is_public", "updated_at"])
        response = self.client.get("/api/v1/doctors/", HTTP_HOST="patient.hms.test")
        self.assertEqual(response.status_code, 200)
        ids = [doc["id"] for doc in response.json()]
        self.assertIn(self.doctor_profile.pk, ids)

    def test_historical_clinical_relationships_preserved(self):
        """Updating doctor profile retains foreign key links to existing appointments and clinical data."""
        from django.utils import timezone
        from core.models import Patient, VisitType
        patient = Patient.objects.create(
            mrn="MRN-TEST-001",
            full_name="Anita Roy",
            phone="+919876543210",
        )
        visit_type = VisitType.objects.create(code="OPD_GEN", name="General OPD")
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=self.doctor_profile,
            visit_type=visit_type,
            scheduled_at=timezone.now(),
            status="scheduled",
        )
        self.doctor_profile.job_title = "Professor & Head of Cardiology"
        self.doctor_profile.save(update_fields=["job_title", "updated_at"])

        appointment.refresh_from_db()
        self.assertEqual(appointment.doctor_id, self.doctor_profile.pk)
        self.assertEqual(appointment.doctor.job_title, "Professor & Head of Cardiology")

    def test_unauthorized_user_cannot_access_doctor_cms(self):
        """Non-admin and patient portal users cannot access doctor admin management."""
        self.client.force_login(self.patient_user)
        response = self.client.get("/admin/core/staffprofile/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)

    def test_xss_content_escaped(self):
        """XSS payloads in qualifications or biography are safely HTML escaped in changelist."""
        self.doctor_profile.qualifications = "<script>alert('xss')</script> MBBS"
        self.doctor_profile.save(update_fields=["qualifications", "updated_at"])

        self.client.force_login(self.admin_user)
        response = self.client.get(f"/admin/core/staffprofile/{self.doctor_profile.pk}/change/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("<script>alert('xss')</script>", content)
        self.assertIn(html.escape(self.doctor_profile.qualifications), content)
