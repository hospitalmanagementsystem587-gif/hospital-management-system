from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import NumberSequence, Patient, Ticket
from core.services.numbering import next_number

User = get_user_model()


class TicketDomainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_patient = User.objects.create_user("patient_user", password="password")
        cls.user_staff = User.objects.create_user("staff_user", password="password")

        cls.patient = Patient.objects.create(
            mrn="PAT-TCK-001",
            full_name="Rajesh Kumar",
        )

        NumberSequence.objects.create(code="TICKET", prefix="TCK-", next_value=1000)

    def test_ticket_creation_and_number_sequence(self):
        t1 = Ticket.objects.create(
            title="Billing discrepancy for OPD invoice",
            description="Double charge recorded on credit card.",
            category=Ticket.Category.BILLING,
            priority=Ticket.Priority.HIGH,
            created_by=self.user_patient,
            patient=self.patient,
        )
        self.assertEqual(t1.number, "TCK-1000")
        self.assertEqual(t1.status, Ticket.Status.OPEN)
        self.assertIsNone(t1.resolved_at)
        self.assertIsNone(t1.closed_at)

        t2 = Ticket.objects.create(
            title="Pharmacy refill query",
            description="Need clarification on antibiotic course duration.",
            category=Ticket.Category.PHARMACY,
            priority=Ticket.Priority.NORMAL,
            created_by=self.user_patient,
            patient=self.patient,
        )
        self.assertEqual(t2.number, "TCK-1001")

    def test_lifecycle_timestamps_on_resolved_and_closed(self):
        t = Ticket.objects.create(
            title="Technical login issue",
            description="Cannot reset portal password.",
            category=Ticket.Category.TECHNICAL,
            priority=Ticket.Priority.NORMAL,
            created_by=self.user_patient,
        )
        self.assertEqual(t.status, Ticket.Status.OPEN)
        self.assertIsNone(t.resolved_at)

        # Transition to resolved
        t.status = Ticket.Status.RESOLVED
        t.save()
        self.assertIsNotNone(t.resolved_at)
        self.assertIsNone(t.closed_at)

        # Transition to closed
        t.status = Ticket.Status.CLOSED
        t.save()
        self.assertIsNotNone(t.closed_at)

        # Reopen
        t.status = Ticket.Status.IN_PROGRESS
        t.save()
        self.assertIsNone(t.resolved_at)
        self.assertIsNone(t.closed_at)

    def test_status_constraint_validation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ticket.objects.create(
                title="Invalid status ticket",
                description="Testing constraint",
                status="invalid_status",
                created_by=self.user_staff,
            )

    def test_priority_constraint_validation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ticket.objects.create(
                title="Invalid priority ticket",
                description="Testing constraint",
                priority="extreme_critical",
                created_by=self.user_staff,
            )

    def test_category_constraint_validation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ticket.objects.create(
                title="Invalid category ticket",
                description="Testing constraint",
                category="finance_arbitrary",
                created_by=self.user_staff,
            )

    def test_ticket_str_representation(self):
        t = Ticket.objects.create(
            title="General lab timing inquiry",
            description="What are Sunday timings for blood draw?",
            category=Ticket.Category.GENERAL,
            created_by=self.user_patient,
        )
        self.assertEqual(str(t), f"{t.number}: General lab timing inquiry (Open)")
