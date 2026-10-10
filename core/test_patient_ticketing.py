from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import Patient, PatientAccount, Ticket, TicketAttachment, TicketMessage
from core.services.ticketing import create_patient_ticket

User = get_user_model()


@override_settings(PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK="core.test_ticket_security.clean_scan")
class PatientTicketCreationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Patient 1 (Verified)
        cls.p1 = Patient.objects.create(mrn="PAT-TCK-001", full_name="Alice Verified")
        cls.u1 = User.objects.create_user("alice", password="password123")
        cls.a1 = PatientAccount.objects.create(user=cls.u1, patient=cls.p1, is_verified=True)

        # Patient 2 (Verified)
        cls.p2 = Patient.objects.create(mrn="PAT-TCK-002", full_name="Bob Verified")
        cls.u2 = User.objects.create_user("bob", password="password123")
        cls.a2 = PatientAccount.objects.create(user=cls.u2, patient=cls.p2, is_verified=True)

        # Patient 3 (Unverified)
        cls.p3 = Patient.objects.create(mrn="PAT-TCK-003", full_name="Charlie Unverified")
        cls.u3 = User.objects.create_user("charlie", password="password123")
        cls.a3 = PatientAccount.objects.create(user=cls.u3, patient=cls.p3, is_verified=False)

    def test_verified_patient_can_create_ticket_via_portal(self):
        self.client.force_login(self.u1)
        resp = self.client.get("/tickets/create/", HTTP_HOST="patient.localhost")
        self.assertEqual(resp.status_code, 200)

        post_data = {
            "title": "Need Billing Clarification",
            "description": "Please check my invoice for ward bed charges.",
            "category": Ticket.Category.BILLING,
            "priority": Ticket.Priority.NORMAL,
        }
        resp = self.client.post("/tickets/create/", post_data, HTTP_HOST="patient.localhost")
        self.assertEqual(resp.status_code, 302)

        ticket = Ticket.objects.filter(patient=self.p1).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.title, "Need Billing Clarification")
        self.assertEqual(ticket.created_by, self.u1)
        self.assertEqual(ticket.patient, self.p1)
        self.assertEqual(ticket.status, Ticket.Status.OPEN)

    def test_unverified_patient_cannot_access_or_create_tickets(self):
        self.client.force_login(self.u3)
        resp = self.client.get("/tickets/create/", HTTP_HOST="patient.localhost")
        self.assertEqual(resp.status_code, 403)

        resp = self.client.post(
            "/tickets/create/",
            {"title": "Fail", "description": "Fail", "category": "general"},
            HTTP_HOST="patient.localhost",
        )
        self.assertEqual(resp.status_code, 403)

    def test_cross_patient_ticket_isolation(self):
        # Alice creates a ticket
        t1 = create_patient_ticket(
            patient=self.p1,
            user=self.u1,
            title="Alice Private Ticket",
            description="Alice medical query",
            category=Ticket.Category.CLINICAL,
        )

        # Bob logs in and checks ticket list
        self.client.force_login(self.u2)
        resp = self.client.get("/tickets/", HTTP_HOST="patient.localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, t1.title)
        self.assertNotContains(resp, t1.number)

        # Bob tries to access Alice's ticket directly
        resp = self.client.get(f"/tickets/{t1.pk}/", HTTP_HOST="patient.localhost")
        self.assertEqual(resp.status_code, 404)

        # Bob tries to post reply to Alice's ticket
        resp = self.client.post(
            f"/tickets/{t1.pk}/",
            {"action": "reply", "body": "Hacked reply"},
            HTTP_HOST="patient.localhost",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(t1.messages.filter(author=self.u2).exists())

    def test_patient_cannot_view_internal_notes_or_internal_attachments(self):
        ticket = create_patient_ticket(
            patient=self.p1,
            user=self.u1,
            title="Ticket with notes",
            description="Details",
            category=Ticket.Category.GENERAL,
        )

        # Support agent creates an internal note and an internal attachment
        staff_user = User.objects.create_user("support_agent")
        TicketMessage.objects.create(
            ticket=ticket,
            author=staff_user,
            body="SECRET_INTERNAL_STAFF_NOTE_1234",
            is_internal=True,
        )
        TicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=staff_user,
            file_name="internal_investigation.pdf",
            size_bytes=100,
            content_type="application/pdf",
            is_internal=True,
        )

        # Public reply
        TicketMessage.objects.create(
            ticket=ticket,
            author=staff_user,
            body="Hello Alice, we received your inquiry.",
            is_internal=False,
        )

        self.client.force_login(self.u1)
        resp = self.client.get(f"/tickets/{ticket.pk}/", HTTP_HOST="patient.localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hello Alice, we received your inquiry.")
        self.assertNotContains(resp, "SECRET_INTERNAL_STAFF_NOTE_1234")
        self.assertNotContains(resp, "internal_investigation.pdf")

    def test_patient_reply_adds_public_message(self):
        ticket = create_patient_ticket(
            patient=self.p1,
            user=self.u1,
            title="Follow-up ticket",
            description="Initial details",
            category=Ticket.Category.GENERAL,
        )

        self.client.force_login(self.u1)
        resp = self.client.post(
            f"/tickets/{ticket.pk}/",
            {"action": "reply", "body": "Thank you for the update!"},
            HTTP_HOST="patient.localhost",
        )
        self.assertEqual(resp.status_code, 302)

        msg = ticket.messages.filter(author=self.u1).first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.body, "Thank you for the update!")
        self.assertFalse(msg.is_internal)
