from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import AuditEvent, Department, StaffProfile


class AuditEventProtectionTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="audit-actor")
        department = Department.objects.create(code="AUD", name="Audit")
        self.actor = StaffProfile.objects.create(
            user=user, employee_id="AUD-001", department=department
        )
        self.event = AuditEvent.objects.create(
            actor=self.actor,
            action="security.permission_reviewed",
            target_type="user",
            target_id=str(user.pk),
            details={"changed_fields": ["groups"]},
        )

    def test_audit_event_is_append_only(self):
        self.event.action = "security.event_tampered"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            self.event.save()
        self.event.refresh_from_db()
        self.assertEqual(self.event.action, "security.permission_reviewed")

    def test_audit_event_cannot_be_deleted_through_model_api(self):
        with self.assertRaisesMessage(ValidationError, "immutable"):
            self.event.delete()
        self.assertTrue(AuditEvent.objects.filter(pk=self.event.pk).exists())

    def test_audit_payload_contains_context_without_secret_material(self):
        self.assertEqual(self.event.actor, self.actor)
        self.assertEqual(self.event.target_type, "user")
        self.assertEqual(self.event.details, {"changed_fields": ["groups"]})
        self.assertNotIn("password", self.event.details)
        self.assertIsNotNone(self.event.created_at)
