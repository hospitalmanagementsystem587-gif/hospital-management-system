import hashlib

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import NumberSequence, Patient, Ticket, TicketAttachment, TicketMessage

User = get_user_model()


class TicketAttachmentDomainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.patient_user = User.objects.create_user("patient_att_user", password="password")
        cls.staff_user = User.objects.create_user("staff_att_user", password="password")

        cls.patient = Patient.objects.create(
            mrn="PAT-TCK-ATT-001",
            full_name="Deepak Sharma",
        )

        NumberSequence.objects.create(code="TICKET", prefix="TCK-", next_value=3000)

        cls.ticket = Ticket.objects.create(
            title="Insurance pre-auth card upload",
            description="Attached copy of insurance card.",
            category=Ticket.Category.BILLING,
            priority=Ticket.Priority.HIGH,
            created_by=cls.patient_user,
            patient=cls.patient,
        )

        cls.message = TicketMessage.objects.create(
            ticket=cls.ticket,
            author=cls.patient_user,
            body="Here is my card scan.",
        )

    def test_attachment_creation_and_attributes(self):
        payload = b"%PDF-1.4 sample insurance card content"
        sha = hashlib.sha256(payload).hexdigest()

        att = TicketAttachment.objects.create(
            ticket=self.ticket,
            message=self.message,
            uploaded_by=self.patient_user,
            file=ContentFile(payload, name="card.pdf"),
            file_name="card.pdf",
            content_type="application/pdf",
            size_bytes=len(payload),
            sha256=sha,
            scan_status=TicketAttachment.MalwareScanStatus.CLEAN,
        )

        self.assertEqual(att.ticket, self.ticket)
        self.assertEqual(att.message, self.message)
        self.assertEqual(att.uploaded_by, self.patient_user)
        self.assertEqual(att.size_bytes, len(payload))
        self.assertEqual(att.sha256, sha)
        self.assertEqual(att.scan_status, TicketAttachment.MalwareScanStatus.CLEAN)
        self.assertIn("card.pdf", str(att))

    def test_scan_status_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TicketAttachment.objects.create(
                ticket=self.ticket,
                uploaded_by=self.patient_user,
                file=ContentFile(b"data", name="test.txt"),
                file_name="test.txt",
                content_type="text/plain",
                size_bytes=4,
                scan_status="malware_arbitrary",
            )

    def test_size_bytes_positive_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TicketAttachment.objects.create(
                ticket=self.ticket,
                uploaded_by=self.patient_user,
                file=ContentFile(b"", name="empty.txt"),
                file_name="empty.txt",
                content_type="text/plain",
                size_bytes=0,
                scan_status=TicketAttachment.MalwareScanStatus.CLEAN,
            )

    def test_quarantined_or_rejected_filtering(self):
        payload = b"%PDF-1.4 valid"
        clean_att = TicketAttachment.objects.create(
            ticket=self.ticket,
            uploaded_by=self.patient_user,
            file=ContentFile(payload, name="clean.pdf"),
            file_name="clean.pdf",
            content_type="application/pdf",
            size_bytes=len(payload),
            scan_status=TicketAttachment.MalwareScanStatus.CLEAN,
        )

        infected_att = TicketAttachment.objects.create(
            ticket=self.ticket,
            uploaded_by=self.patient_user,
            file=ContentFile(b"dangerous malware payload", name="bad.exe"),
            file_name="bad.exe",
            content_type="application/octet-stream",
            size_bytes=25,
            scan_status=TicketAttachment.MalwareScanStatus.REJECTED,
        )

        clean_only = self.ticket.attachments.filter(scan_status=TicketAttachment.MalwareScanStatus.CLEAN)
        self.assertIn(clean_att, clean_only)
        self.assertNotIn(infected_att, clean_only)
