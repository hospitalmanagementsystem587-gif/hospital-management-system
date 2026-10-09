import hashlib

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import (
    Department, Invoice, Patient, PatientAccount, PatientDocument,
    StaffProfile, Ticket, TicketAttachment, TicketMessage,
)
from core.roles import configure_role_permissions

User = get_user_model()


@override_settings(
    PORTAL_HOSTS={"admin": "admin.hms.test", "staff": "staff.hms.test", "store": "store.hms.test", "patient": "patient.hms.test", "agent": "agent.hms.test"},
    ALLOWED_HOSTS=["testserver", ".hms.test"],
)
class ObjectLevelAccessMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()
        cls.dept_a = Department.objects.create(code="SEC-A", name="Security A")
        cls.dept_b = Department.objects.create(code="SEC-B", name="Security B")
        cls.patient_a = Patient.objects.create(mrn="OBJ-A", full_name="Patient A")
        cls.patient_b = Patient.objects.create(mrn="OBJ-B", full_name="Patient B")
        cls.user_a = User.objects.create_user("object_patient_a", password="Password123!")
        cls.user_b = User.objects.create_user("object_patient_b", password="Password123!")
        PatientAccount.objects.create(user=cls.user_a, patient=cls.patient_a, is_verified=True)
        PatientAccount.objects.create(user=cls.user_b, patient=cls.patient_b, is_verified=True)
        cls.agent_a = User.objects.create_user("object_agent_a", password="Password123!")
        cls.agent_b = User.objects.create_user("object_agent_b", password="Password123!")
        support = Group.objects.get(name="Support Agent")
        cls.agent_a.groups.add(support)
        cls.agent_b.groups.add(support)
        cls.profile_a = StaffProfile.objects.create(user=cls.agent_a, employee_id="OBJ-AA", department=cls.dept_a)
        cls.profile_b = StaffProfile.objects.create(user=cls.agent_b, employee_id="OBJ-AB", department=cls.dept_b)
        cls.ticket_a = Ticket.objects.create(
            title="Department A", description="private", created_by=cls.user_a,
            patient=cls.patient_a, assigned_team=cls.dept_a,
        )
        TicketMessage.objects.create(ticket=cls.ticket_a, author=cls.agent_a, body="internal secret", is_internal=True)
        cls.internal_attachment = TicketAttachment.objects.create(
            ticket=cls.ticket_a, uploaded_by=cls.agent_a,
            file=ContentFile(b"%PDF-1.4 internal", name="internal.pdf"),
            file_name="internal.pdf", content_type="application/pdf", size_bytes=17,
            sha256=hashlib.sha256(b"%PDF-1.4 internal").hexdigest(),
            scan_status=TicketAttachment.MalwareScanStatus.CLEAN, is_internal=True,
        )
        cls.invoice_a = Invoice.objects.create(patient=cls.patient_a, number="OBJ-INV-A", status=Invoice.Status.ISSUED)
        cls.invoice_b = Invoice.objects.create(patient=cls.patient_b, number="OBJ-INV-B", status=Invoice.Status.ISSUED)
        content = b"%PDF-1.4 patient B"
        cls.document_b = PatientDocument.objects.create(
            patient=cls.patient_b, title="Patient B report", document_type=PatientDocument.DocumentType.LAB_REPORT,
            file=ContentFile(content, name="b.pdf"), content_type="application/pdf", size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(), validation_status=PatientDocument.ValidationStatus.CLEAN,
            patient_released_at=timezone.now(),
        )

    def _api_as(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return client

    def test_patient_direct_web_ticket_identifier_is_isolated(self):
        client = Client(HTTP_HOST="patient.hms.test")
        client.force_login(self.user_b)
        self.assertEqual(client.get(f"/tickets/{self.ticket_a.pk}/").status_code, 404)

    def test_patient_api_invoice_identifier_is_isolated(self):
        response = self._api_as(self.user_a).get(f"/api/v1/me/invoices/{self.invoice_b.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_patient_api_document_identifier_is_isolated(self):
        response = self._api_as(self.user_a).get(
            f"/api/v1/me/documents/{self.document_b.public_id}/download/"
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_department_agent_direct_url_is_denied(self):
        client = Client(HTTP_HOST="agent.hms.test")
        client.force_login(self.agent_b)
        self.assertEqual(client.get(f"/tickets/{self.ticket_a.pk}/").status_code, 403)

    def test_patient_page_hides_internal_message_and_attachment(self):
        client = Client(HTTP_HOST="patient.hms.test")
        client.force_login(self.user_a)
        response = client.get(f"/tickets/{self.ticket_a.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "internal secret")
        self.assertNotContains(response, "internal.pdf")

    def test_patient_ticket_mutation_requires_csrf(self):
        client = Client(HTTP_HOST="patient.hms.test", enforce_csrf_checks=True)
        client.force_login(self.user_a)
        response = client.post(f"/tickets/{self.ticket_a.pk}/", {"action": "reply", "body": "no csrf"})
        self.assertEqual(response.status_code, 403)
