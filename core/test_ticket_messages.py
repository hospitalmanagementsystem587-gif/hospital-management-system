from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import NumberSequence, Patient, Ticket, TicketMessage

User = get_user_model()


class TicketMessageDomainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.patient_user = User.objects.create_user("patient_user_msg", password="password")
        cls.staff_user_1 = User.objects.create_user("staff_support_1", password="password")
        cls.staff_user_2 = User.objects.create_user("staff_support_2", password="password")

        cls.patient = Patient.objects.create(
            mrn="PAT-TCK-MSG-001",
            full_name="Pooja Hegde",
        )

        NumberSequence.objects.create(code="TICKET", prefix="TCK-", next_value=2000)

        cls.ticket = Ticket.objects.create(
            title="Prescription clarification",
            description="Need clarification on dosage timings.",
            category=Ticket.Category.PHARMACY,
            priority=Ticket.Priority.NORMAL,
            created_by=cls.patient_user,
            patient=cls.patient,
        )

    def test_message_ordering_and_attribution(self):
        msg1 = TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.patient_user,
            body="Hello, should I take the red capsule before or after breakfast?",
            is_internal=False,
        )
        msg2 = TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.staff_user_1,
            body="Checked patient consultation history: doctor prescribed post-meal.",
            is_internal=True,
        )
        msg3 = TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.staff_user_1,
            body="Dear Pooja, please take the medication 30 minutes after your meal.",
            is_internal=False,
        )

        messages = list(self.ticket.messages.all())
        self.assertEqual(messages, [msg1, msg2, msg3])
        self.assertEqual(msg1.author, self.patient_user)
        self.assertFalse(msg1.is_internal)
        self.assertTrue(msg2.is_internal)
        self.assertFalse(msg3.is_internal)

    def test_patient_visibility_filtering(self):
        # Create external and internal messages
        TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.patient_user,
            body="Public inquiry",
            is_internal=False,
        )
        TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.staff_user_1,
            body="Internal triage: assigning to pharmacy desk",
            is_internal=True,
        )
        TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.staff_user_2,
            body="Public response to patient",
            is_internal=False,
        )

        # Patient-facing queryset (must exclude internal messages)
        patient_visible = self.ticket.messages.filter(is_internal=False)
        self.assertEqual(patient_visible.count(), 2)
        for m in patient_visible:
            self.assertFalse(m.is_internal)

        # Staff-facing queryset (includes internal and external)
        staff_visible = self.ticket.messages.all()
        self.assertEqual(staff_visible.count(), 3)

    def test_ticket_message_str(self):
        msg_public = TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.patient_user,
            body="Public question",
            is_internal=False,
        )
        self.assertEqual(
            str(msg_public),
            f"{self.ticket.number} - Reply by {self.patient_user.username}",
        )

        msg_internal = TicketMessage.objects.create(
            ticket=self.ticket,
            author=self.staff_user_1,
            body="Confidential staff note",
            is_internal=True,
        )
        self.assertEqual(
            str(msg_internal),
            f"{self.ticket.number} - Internal note by {self.staff_user_1.username}",
        )
