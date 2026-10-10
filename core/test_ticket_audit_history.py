from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models import Department, Patient, PatientAccount, StaffProfile, Ticket
from core.services.ticketing import create_patient_ticket, ticket_history_for_user

User = get_user_model()


class TicketAuditHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.patient = Patient.objects.create(mrn="AUD-1", full_name="Audit Patient")
        cls.patient_user = User.objects.create_user("audit_patient")
        PatientAccount.objects.create(user=cls.patient_user, patient=cls.patient, is_verified=True)
        cls.other_patient = User.objects.create_user("audit_other")
        cls.department = Department.objects.create(code="AUDIT", name="Audit Support")
        cls.agent = User.objects.create_user("audit_agent")
        cls.profile = StaffProfile.objects.create(user=cls.agent, employee_id="AUD-A1", department=cls.department)
        perms = Permission.objects.filter(
            content_type__app_label="core",
            codename__in=["view_ticket", "change_ticket", "view_ticketauditevent", "view_internal_ticketaudit"],
        )
        cls.agent.user_permissions.add(*perms)

    def setUp(self):
        self.ticket = create_patient_ticket(
            patient=self.patient, user=self.patient_user, title="Audit me",
            description="Audit lifecycle", category=Ticket.Category.GENERAL,
        )

    def test_status_assignment_and_priority_capture_actor_and_values(self):
        self.ticket.assign(staff_profile=self.profile, team=self.department, actor=self.agent, reason="triage")
        self.ticket.change_priority(Ticket.Priority.HIGH, actor=self.agent, reason="clinical urgency")
        self.ticket.transition_to(Ticket.Status.IN_PROGRESS, actor=self.agent, reason="accepted")
        history = list(self.ticket.audit_history.all())
        self.assertEqual([event.action for event in history], ["created", "assignment_changed", "priority_changed", "status_changed"])
        self.assertTrue(all(event.actor_id for event in history))
        self.assertEqual(history[2].previous_value, Ticket.Priority.NORMAL)
        self.assertEqual(history[2].new_value, Ticket.Priority.HIGH)

    def test_patient_sees_only_patient_appropriate_history(self):
        self.ticket.assign(staff_profile=self.profile, team=self.department, actor=self.agent, reason="private routing")
        self.ticket.transition_to(Ticket.Status.IN_PROGRESS, actor=self.agent, reason="accepted")
        actions = list(ticket_history_for_user(self.ticket, self.patient_user).values_list("action", flat=True))
        self.assertEqual(actions, ["created", "status_changed"])
        with self.assertRaises(PermissionDenied):
            ticket_history_for_user(self.ticket, self.other_patient)

    def test_agent_can_read_internal_history_and_records_are_immutable(self):
        self.ticket.assign(staff_profile=self.profile, team=self.department, actor=self.agent)
        history = ticket_history_for_user(self.ticket, self.agent)
        event = history.get(action="assignment_changed")
        event.reason = "tampered"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
