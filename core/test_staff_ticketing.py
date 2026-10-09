import io
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from core.models import (
    Department,
    Patient,
    PatientAccount,
    StaffProfile,
    Ticket,
    TicketAttachment,
    TicketMessage,
)
from core.roles import configure_role_permissions
from core.services.ticketing import create_staff_ticket, staff_tickets_queryset

User = get_user_model()


class StaffTicketingTests(TestCase):
    def setUp(self):
        configure_role_permissions()

        self.dept_cardio = Department.objects.create(name="Cardiology", code="CARD")
        self.dept_neuro = Department.objects.create(name="Neurology", code="NEUR")

        self.doctor_user = User.objects.create_user(
            username="doc_smith", email="doc@example.com", password="password123"
        )
        doctor_group = Group.objects.get(name="Doctor")
        self.doctor_user.groups.add(doctor_group)
        self.doctor_staff = StaffProfile.objects.create(
            user=self.doctor_user,
            employee_id="DOC-93-01",
            department=self.dept_cardio,
            job_title="Cardiologist",
        )

        self.reception_user = User.objects.create_user(
            username="recep_jane", email="recep@example.com", password="password123"
        )
        reception_group = Group.objects.get(name="Reception")
        self.reception_user.groups.add(reception_group)
        self.reception_staff = StaffProfile.objects.create(
            user=self.reception_user,
            employee_id="REC-93-01",
            department=self.dept_cardio,
            job_title="Receptionist",
        )

        self.other_doctor_user = User.objects.create_user(
            username="doc_neuro", email="neuro@example.com", password="password123"
        )
        self.other_doctor_user.groups.add(doctor_group)
        self.other_doctor_staff = StaffProfile.objects.create(
            user=self.other_doctor_user,
            employee_id="DOC-93-02",
            department=self.dept_neuro,
            job_title="Neurologist",
        )

        self.patient = Patient.objects.create(
            mrn="PAT-93-01",
            full_name="John Doe",
        )

        self.patient_user = User.objects.create_user(
            username="pat_john", email="pat@example.com", password="password123"
        )
        PatientAccount.objects.create(
            user=self.patient_user,
            patient=self.patient,
            is_verified=True,
        )

        self.client = Client()

    def test_create_staff_ticket_service(self):
        ticket = create_staff_ticket(
            user=self.doctor_user,
            title="Cardio review needed",
            description="Patient needs evaluation",
            category=Ticket.Category.CLINICAL,
            priority=Ticket.Priority.URGENT,
            assigned_team=self.dept_cardio,
            patient=self.patient,
        )
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.created_by, self.doctor_user)
        self.assertEqual(ticket.assigned_team, self.dept_cardio)
        self.assertEqual(ticket.patient, self.patient)
        self.assertEqual(ticket.priority, Ticket.Priority.URGENT)
        self.assertEqual(ticket.description, "Patient needs evaluation")

    def test_staff_tickets_queryset_scoping(self):
        t1 = create_staff_ticket(
            user=self.doctor_user,
            title="Cardio 1",
            description="Desc",
            assigned_team=self.dept_cardio,
            category=Ticket.Category.CLINICAL,
            patient=self.patient,
        )
        t2 = create_staff_ticket(
            user=self.other_doctor_user,
            title="Neuro 1",
            description="Desc",
            assigned_team=self.dept_neuro,
            category=Ticket.Category.CLINICAL,
        )

        # doctor in cardio sees t1, but not t2
        qs_cardio = staff_tickets_queryset(self.doctor_user)
        self.assertIn(t1, qs_cardio)
        self.assertNotIn(t2, qs_cardio)

        # doctor in neuro sees t2, but not t1
        qs_neuro = staff_tickets_queryset(self.other_doctor_user)
        self.assertIn(t2, qs_neuro)
        self.assertNotIn(t1, qs_neuro)

    def test_staff_ticket_views_and_internal_notes(self):
        self.client.force_login(self.doctor_user)

        # Create ticket via view
        resp = self.client.post(
            reverse("staff_ticket_create"),
            {
                "title": "Follow up consultation",
                "category": Ticket.Category.CLINICAL,
                "priority": Ticket.Priority.HIGH,
                "assigned_team": self.dept_cardio.pk,
                "patient": self.patient.pk,
                "description": "Patient reports chest pain",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        ticket = Ticket.objects.get(title="Follow up consultation")
        self.assertEqual(ticket.assigned_team, self.dept_cardio)
        self.assertEqual(ticket.patient, self.patient)

        # Add an internal note message via ticket detail view
        resp = self.client.post(
            reverse("staff_ticket_detail", args=[ticket.pk]),
            {
                "body": "Private doctor observation: check ECG results",
                "is_internal": "true",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ticket.messages.count(), 1)
        note = ticket.messages.filter(body="Private doctor observation: check ECG results").first()
        self.assertIsNotNone(note)
        self.assertTrue(note.is_internal)

        # Add a public message
        resp = self.client.post(
            reverse("staff_ticket_detail", args=[ticket.pk]),
            {
                "body": "Public instructions: please rest and drink water",
                "is_internal": "false",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        pub_msg = ticket.messages.filter(body="Public instructions: please rest and drink water").first()
        self.assertIsNotNone(pub_msg)
        self.assertFalse(pub_msg.is_internal)

        # Verify patient isolation: patient cannot see internal note
        self.client.force_login(self.patient_user)
        resp_pat = self.client.get(f"/tickets/{ticket.pk}/", HTTP_HOST="patient.localhost")
        self.assertEqual(resp_pat.status_code, 200)
        self.assertContains(resp_pat, "Public instructions: please rest and drink water")
        self.assertNotContains(resp_pat, "Private doctor observation: check ECG results")

    def test_staff_ticket_attachment_upload(self):
        self.client.force_login(self.doctor_user)
        ticket = create_staff_ticket(
            user=self.doctor_user,
            title="Test upload",
            description="Desc",
            assigned_team=self.dept_cardio,
            category=Ticket.Category.CLINICAL,
            patient=self.patient,
        )
        dummy_file = SimpleUploadedFile("report.pdf", b"%PDF-1.4 Healthy vitals test content", content_type="application/pdf")
        resp = self.client.post(
            reverse("staff_ticket_detail", args=[ticket.pk]),
            {
                "body": "Uploading confidential lab report",
                "is_internal": "true",
                "attachment": dummy_file,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        att = TicketAttachment.objects.filter(file_name="report.pdf").first()
        self.assertIsNotNone(att)
        self.assertTrue(att.is_internal)

    def test_unauthenticated_and_non_staff_denied(self):
        # Anonymous
        resp = self.client.get(reverse("staff_ticket_list"))
        self.assertEqual(resp.status_code, 302)

        # Patient user trying to access staff portal ticket views
        self.client.force_login(self.patient_user)
        resp = self.client.get(reverse("staff_ticket_list"))
        self.assertEqual(resp.status_code, 403)

        resp = self.client.get(reverse("staff_ticket_create"))
        self.assertEqual(resp.status_code, 403)
