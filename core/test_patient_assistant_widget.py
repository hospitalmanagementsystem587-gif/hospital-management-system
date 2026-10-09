from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import Patient, PatientAccount


@override_settings(
    PORTAL_HOSTS={
        "admin": "admin.hms.test",
        "staff": "staff.hms.test",
        "store": "store.hms.test",
        "patient": "patient.hms.test",
        "agent": "agent.hms.test",
    },
    ALLOWED_HOSTS=["testserver", ".hms.test"],
)
class PatientAssistantWidgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("guide-patient")
        patient = Patient.objects.create(mrn="GUIDE-001", full_name="Guide Patient")
        PatientAccount.objects.create(user=cls.user, patient=patient, is_verified=True)

    def test_widget_is_available_only_inside_authenticated_patient_portal(self):
        self.client.force_login(self.user)
        response = self.client.get("/", HTTP_HOST="patient.hms.test")
        self.assertContains(response, 'data-care-guide')
        self.assertContains(response, 'patient-assistant.')
        self.assertContains(response, '.js?v=1')
        self.assertContains(response, '.css?v=1')

        response = self.client.get("/health/", HTTP_HOST="staff.hms.test")
        self.assertNotContains(response, 'data-care-guide')

    def test_widget_has_accessible_controls_and_safety_boundaries(self):
        self.client.force_login(self.user)
        response = self.client.get("/", HTTP_HOST="patient.hms.test")
        self.assertContains(response, 'aria-controls="care-guide-panel"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(response, 'Portal help—not medical advice')
        self.assertContains(response, 'emergency services directly')
        self.assertContains(response, 'No patient information leaves this page.')

    def test_widget_links_resolve_to_existing_patient_workflows(self):
        self.client.force_login(self.user)
        response = self.client.get("/", HTTP_HOST="patient.hms.test")
        for label in (
            "Book an appointment",
            "Find reports",
            "View prescriptions",
            "Contact support",
        ):
            self.assertContains(response, label)
