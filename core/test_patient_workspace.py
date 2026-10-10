from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    AuditEvent,
    NumberSequence,
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
class PatientWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        NumberSequence.objects.create(
            code="PATIENT",
            prefix="PAT-",
            next_value=100,
        )

        # Doctor 1
        cls.doctor1_user = User.objects.create_user("doc1_user", password="password")
        cls.doctor1_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor1_profile = StaffProfile.objects.create(
            user=cls.doctor1_user,
            employee_id="DOC001",
        )

        # Doctor 2
        cls.doctor2_user = User.objects.create_user("doc2_user", password="password")
        cls.doctor2_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doctor2_profile = StaffProfile.objects.create(
            user=cls.doctor2_user,
            employee_id="DOC002",
        )

        # Reception
        cls.reception_user = User.objects.create_user("rec_user", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC001",
        )

        # Administrator
        cls.admin_user = User.objects.create_user("adm_user", password="password", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM001",
        )

        # Pharmacy user (restricted from general patient workspace)
        cls.pharmacy_user = User.objects.create_user("phm_user", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM001",
        )

        # Patients
        cls.patient1 = Patient.objects.create(
            mrn="PAT-000001",
            full_name="Alice Assigned",
            phone="9876543210",
            allergy_safety_notes="Severe Penicillin allergy",
        )
        cls.patient2 = Patient.objects.create(
            mrn="PAT-000002",
            full_name="Bob Other",
            phone="9876543211",
        )
        cls.archived_patient = Patient.objects.create(
            mrn="PAT-000003",
            full_name="Charlie Archived",
            phone="9876543212",
            archived_at=timezone.now(),
        )

        cls.visit_type = VisitType.objects.create(name="Consultation", code="CONSULT")

        # Assign patient1 to Doctor 1 via Appointment
        Appointment.objects.create(
            patient=cls.patient1,
            doctor=cls.doctor1_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
            status=Appointment.Status.SCHEDULED,
        )

    def test_anonymous_redirects_to_login(self):
        response = self.client.get("/patients/", HTTP_HOST="staff.hms.test")
        self.assertRedirects(response, "/accounts/login/?next=/patients/", fetch_redirect_response=False)

    def test_pharmacy_user_denied_access_to_patient_workspace(self):
        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/patients/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 403)

        response_detail = self.client.get(f"/patients/{self.patient1.pk}/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response_detail.status_code, 403)

    def test_reception_sees_all_non_archived_patients_and_admin_is_denied(self):
        self.client.force_login(self.reception_user)
        response = self.client.get("/patients/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Assigned")
        self.assertContains(response, "Bob Other")
        self.assertNotContains(response, "Charlie Archived")

        self.client.force_login(self.admin_user)
        self.assertEqual(
            self.client.get("/patients/", HTTP_HOST="staff.hms.test").status_code,
            403,
        )

    def test_doctor_sees_only_assigned_or_clinical_patients(self):
        self.client.force_login(self.doctor1_user)
        response = self.client.get("/patients/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Assigned")
        self.assertNotContains(response, "Bob Other")
        self.assertNotContains(response, "Charlie Archived")

        # Doctor 2 has no assigned appointments or consultations
        self.client.force_login(self.doctor2_user)
        res_doc2 = self.client.get("/patients/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_doc2.status_code, 200)
        self.assertNotContains(res_doc2, "Alice Assigned")
        self.assertNotContains(res_doc2, "Bob Other")

    def test_doctor_cannot_access_unassigned_patient_detail(self):
        self.client.force_login(self.doctor2_user)
        # Doctor 2 attempting to view patient 1
        response = self.client.get(f"/patients/{self.patient1.pk}/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 404)

        # Doctor 1 can access assigned patient 1 detail and view allergy notes
        self.client.force_login(self.doctor1_user)
        res_doc1 = self.client.get(f"/patients/{self.patient1.pk}/", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_doc1.status_code, 200)
        self.assertContains(res_doc1, "Alice Assigned")
        self.assertContains(res_doc1, "Severe Penicillin allergy")

    def test_search_respects_role_scoping(self):
        # Doctor 1 searching for Bob Other gets nothing
        self.client.force_login(self.doctor1_user)
        response = self.client.get("/patients/?q=Bob", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Bob Other")

        # Reception searching for Bob Other finds him
        self.client.force_login(self.reception_user)
        res_rec = self.client.get("/patients/?q=Bob", HTTP_HOST="staff.hms.test")
        self.assertEqual(res_rec.status_code, 200)
        self.assertContains(res_rec, "Bob Other")

    def test_archived_patient_cannot_be_accessed(self):
        self.client.force_login(self.reception_user)
        response = self.client.get(f"/patients/{self.archived_patient.pk}/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 404)

    def test_patient_registration_by_reception_only(self):
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/patients/register/",
            {"full_name": "Dave New", "phone": "9123456780", "age": 28},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        created = Patient.objects.get(full_name="Dave New")
        self.assertTrue(created.mrn.startswith("PAT-"))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="patient.created", target_id=str(created.pk)
            ).exists()
        )

        self.client.force_login(self.admin_user)
        self.assertEqual(
            self.client.post(
                "/patients/register/",
                {"full_name": "Denied Admin", "phone": "9123456781", "age": 28},
                HTTP_HOST="staff.hms.test",
            ).status_code,
            403,
        )

    def test_patient_demographics_update_and_audit(self):
        self.client.force_login(self.reception_user)
        response = self.client.post(
            f"/patients/{self.patient1.pk}/edit/",
            {
                "full_name": "Alice Updated",
                "phone": "9998887776",
                "age": 32,
            },
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 302)
        self.patient1.refresh_from_db()
        self.assertEqual(self.patient1.full_name, "Alice Updated")
        self.assertEqual(self.patient1.phone, "9998887776")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="patient.demographics_updated",
                target_id=str(self.patient1.pk),
            ).exists()
        )

    def test_doctor_cannot_create_or_update_patients(self):
        self.client.force_login(self.doctor1_user)
        res_create = self.client.post(
            "/patients/register/",
            {"full_name": "Doctor Illicit", "phone": "9111111111"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_create.status_code, 403)

        res_update = self.client.post(
            f"/patients/{self.patient1.pk}/edit/",
            {"full_name": "Doctor Hacked", "phone": "9111111111"},
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(res_update.status_code, 403)
