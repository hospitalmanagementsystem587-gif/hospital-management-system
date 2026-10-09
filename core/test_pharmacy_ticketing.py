from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from core.models import (
    Department,
    Patient,
    PatientAccount,
    Prescription,
    StaffProfile,
    Ticket,
    TicketAttachment,
)
from core.roles import configure_role_permissions
from core.services.ticketing import (
    create_staff_ticket,
    staff_tickets_queryset,
    can_access_ticket,
)

User = get_user_model()


class PharmacyTicketingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        cls.dept_pharmacy = Department.objects.create(name="Pharmacy Dept", code="PHARM_DEPT")
        cls.dept_cardio = Department.objects.create(name="Cardiology Dept", code="CARDIO_DEPT")
        cls.dept_billing = Department.objects.create(name="Billing Dept", code="BILLING_DEPT")

        # Pharmacy staff user
        cls.pharm_user = User.objects.create_user(
            username="pharm_tech", email="pharm@hospital.com", password="password123"
        )
        pharm_group = Group.objects.get(name="Pharmacy")
        cls.pharm_user.groups.add(pharm_group)
        cls.pharm_profile = StaffProfile.objects.create(
            user=cls.pharm_user,
            employee_id="PHARM-01",
            department=cls.dept_pharmacy,
            job_title="Pharmacist",
        )

        # Doctor staff user
        cls.doc_user = User.objects.create_user(
            username="doc_cardio", email="doc@hospital.com", password="password123"
        )
        doc_group = Group.objects.get(name="Doctor")
        cls.doc_user.groups.add(doc_group)
        cls.doc_profile = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-PH-01",
            department=cls.dept_cardio,
            job_title="Cardiologist",
        )

        # Patient
        cls.patient = Patient.objects.create(
            mrn="PAT-PHARM-01",
            full_name="Patient Pharmacy Test",
        )
        cls.patient_user = User.objects.create_user(
            username="pat_user", email="pat@hospital.com", password="password123"
        )
        PatientAccount.objects.create(
            user=cls.patient_user,
            patient=cls.patient,
            is_verified=True,
        )

    def setUp(self):
        self.client = Client()

    def test_pharmacy_user_can_create_operational_ticket(self):
        self.client.force_login(self.pharm_user)
        resp = self.client.post(
            reverse("staff_ticket_create"),
            {
                "title": "Low stock alert for Amoxicillin 500mg",
                "category": Ticket.Category.PHARMACY,
                "priority": Ticket.Priority.HIGH,
                "assigned_team": self.dept_pharmacy.pk,
                "description": "Stock count reached reorder point.",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        ticket = Ticket.objects.filter(title="Low stock alert for Amoxicillin 500mg").first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.category, Ticket.Category.PHARMACY)
        self.assertEqual(ticket.assigned_team, self.dept_pharmacy)
        self.assertEqual(ticket.created_by, self.pharm_user)

    def test_pharmacy_user_ticket_queue_context_scoping(self):
        # Pharmacy ticket
        pharm_ticket = create_staff_ticket(
            user=self.pharm_user,
            title="Dispensing discrepancy batch B001",
            description="Details of batch",
            category=Ticket.Category.PHARMACY,
            assigned_team=self.dept_pharmacy,
        )
        # Clinical cardiology ticket
        clinical_ticket = create_staff_ticket(
            user=self.doc_user,
            title="Urgent ECG interpretation",
            description="Details of ECG",
            category=Ticket.Category.CLINICAL,
            assigned_team=self.dept_cardio,
        )

        pharm_qs = staff_tickets_queryset(self.pharm_user)
        self.assertIn(pharm_ticket, pharm_qs)
        self.assertNotIn(clinical_ticket, pharm_qs)

        # Object level check
        self.assertTrue(can_access_ticket(self.pharm_user, pharm_ticket))
        self.assertFalse(can_access_ticket(self.pharm_user, clinical_ticket))

    def test_patient_privacy_minimization_in_pharmacy_ticket(self):
        # Pharmacy user creates ticket linked to patient for medication counseling
        self.client.force_login(self.pharm_user)
        resp = self.client.post(
            reverse("staff_ticket_create"),
            {
                "title": "Patient dosage inquiry",
                "category": Ticket.Category.PHARMACY,
                "priority": Ticket.Priority.NORMAL,
                "assigned_team": self.dept_pharmacy.pk,
                "patient": self.patient.pk,
                "description": "Patient inquired regarding timing of evening dose.",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        ticket = Ticket.objects.get(title="Patient dosage inquiry")
        self.assertEqual(ticket.patient, self.patient)

        # Post an internal pharmacy note
        resp = self.client.post(
            reverse("staff_ticket_detail", args=[ticket.pk]),
            {
                "body": "Pharmacist verified with prescriber: take with food.",
                "is_internal": "true",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        # Patient cannot see the internal pharmacist note in patient portal
        self.client.force_login(self.patient_user)
        pat_resp = self.client.get(f"/tickets/{ticket.pk}/", HTTP_HOST="patient.localhost")
        self.assertEqual(pat_resp.status_code, 200)
        self.assertNotContains(pat_resp, "Pharmacist verified with prescriber")

    def test_pharmacy_dashboard_links_to_tickets(self):
        self.client.force_login(self.pharm_user)
        resp = self.client.get(reverse("pharmacy_dashboard"), HTTP_HOST="store.localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("staff_ticket_list"))
        self.assertContains(resp, reverse("staff_ticket_create"))
