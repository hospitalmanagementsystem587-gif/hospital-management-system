from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from core.models import Department, Patient, PatientAccount, StaffProfile, Ticket, TicketAttachment, TicketMessage
from core.services.ticketing import (
    add_ticket_message,
    can_access_ticket,
    create_ticket_attachment,
    messages_for_user,
    open_ticket_attachment,
)

User = get_user_model()


@override_settings(PATIENT_DOCUMENT_MALWARE_SCAN_CALLBACK="core.test_ticket_security.clean_scan")
class TicketSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(code="SUPPORT", name="Support")
        cls.other_department = Department.objects.create(code="OTHER", name="Other")
        cls.patient = Patient.objects.create(mrn="SEC-001", full_name="Ticket Owner")
        cls.owner = User.objects.create_user("ticket_owner")
        PatientAccount.objects.create(user=cls.owner, patient=cls.patient, is_verified=True)
        cls.other_patient = User.objects.create_user("other_patient")
        cls.agent = User.objects.create_user("ticket_agent")
        cls.other_agent = User.objects.create_user("other_agent")
        cls.inactive_agent = User.objects.create_user("inactive_agent", is_active=False)
        cls.agent_profile = StaffProfile.objects.create(
            user=cls.agent, employee_id="SEC-A1", department=cls.department
        )
        cls.other_profile = StaffProfile.objects.create(
            user=cls.other_agent, employee_id="SEC-A2", department=cls.other_department
        )
        cls.inactive_profile = StaffProfile.objects.create(
            user=cls.inactive_agent, employee_id="SEC-A3", department=cls.department
        )
        ticket_permissions = Permission.objects.filter(
            content_type__app_label="core",
            codename__in=[
                "view_ticket", "change_ticket", "add_ticketmessage",
                "view_ticketmessage", "add_ticketattachment", "view_ticketattachment",
            ],
        )
        cls.agent.user_permissions.add(*ticket_permissions)
        cls.other_agent.user_permissions.add(*ticket_permissions)
        cls.inactive_agent.user_permissions.add(*ticket_permissions)
        cls.ticket = Ticket.objects.create(
            title="Secure ticket", description="Sensitive request", created_by=cls.owner,
            patient=cls.patient, assigned_team=cls.department,
        )

    def test_object_access_is_scoped_to_participant_or_queue(self):
        self.assertTrue(can_access_ticket(self.owner, self.ticket))
        self.assertTrue(can_access_ticket(self.agent, self.ticket))
        self.assertFalse(can_access_ticket(self.other_patient, self.ticket))
        self.assertFalse(can_access_ticket(self.other_agent, self.ticket))

    def test_patient_cannot_create_or_read_internal_note(self):
        with self.assertRaises(PermissionDenied):
            add_ticket_message(
                ticket=self.ticket, author=self.owner, body="hidden", is_internal=True
            )
        public = add_ticket_message(ticket=self.ticket, author=self.owner, body=" public reply ")
        TicketMessage.objects.create(
            ticket=self.ticket, author=self.agent, body="internal", is_internal=True
        )
        self.assertEqual(list(messages_for_user(self.ticket, self.owner)), [public])

    def test_messages_are_append_only(self):
        message = add_ticket_message(ticket=self.ticket, author=self.owner, body="original")
        message.body = "changed"
        with self.assertRaises(ValidationError):
            message.save()
        with self.assertRaises(ValidationError):
            message.delete()

    def test_attachment_upload_validates_content_and_cross_ticket_message(self):
        other_ticket = Ticket.objects.create(
            title="Other", description="Other", created_by=self.owner, patient=self.patient
        )
        other_message = TicketMessage.objects.create(
            ticket=other_ticket, author=self.owner, body="other"
        )
        with self.assertRaises(ValidationError):
            create_ticket_attachment(
                ticket=self.ticket, uploaded_by=self.owner,
                upload=ContentFile(b"executable", name="payload.exe"),
            )
        with self.assertRaises(ValidationError):
            create_ticket_attachment(
                ticket=self.ticket, uploaded_by=self.owner,
                upload=ContentFile(b"%PDF-1.4 valid", name="report.pdf"),
                message=other_message,
            )

    def test_internal_attachment_is_not_patient_accessible(self):
        attachment = create_ticket_attachment(
            ticket=self.ticket, uploaded_by=self.agent,
            upload=ContentFile(b"%PDF-1.4 valid secure report", name="../../report.pdf"),
            is_internal=True,
        )
        self.assertEqual(attachment.file_name, "report.pdf")
        self.assertEqual(attachment.scan_status, TicketAttachment.MalwareScanStatus.CLEAN)
        with self.assertRaises(PermissionDenied):
            open_ticket_attachment(attachment=attachment, user=self.owner)
        handle = open_ticket_attachment(attachment=attachment, user=self.agent)
        self.assertTrue(handle.read().startswith(b"%PDF-"))
        handle.close()

    def test_assignment_rejects_ineligible_agent_and_team_mismatch(self):
        with self.assertRaises(ValidationError):
            self.ticket.assign(staff_profile=self.inactive_profile, actor=self.agent)
        with self.assertRaises(ValidationError):
            self.ticket.assign(
                staff_profile=self.other_profile, team=self.department, actor=self.agent
            )
        with self.assertRaises(PermissionDenied):
            self.ticket.assign(staff_profile=self.agent_profile, actor=self.owner)

    def test_assignment_and_status_changes_are_audited(self):
        self.ticket.assign(
            staff_profile=self.agent_profile, team=self.department,
            actor=self.agent, reason="manual triage",
        )
        self.ticket.transition_to(
            Ticket.Status.IN_PROGRESS, actor=self.agent, reason="work started"
        )
        history = " ".join(self.ticket.messages.values_list("body", flat=True))
        self.assertIn("manual triage", history)
        self.assertIn("work started", history)


def clean_scan(upload):
    return True
