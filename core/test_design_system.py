import os
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.test import RequestFactory, TestCase, override_settings
from django.template.loader import render_to_string
from django.utils import timezone

from core.context_processors import hospital_context
from core.models import HospitalSettings, Patient, PatientAccount, StaffProfile

User = get_user_model()


class SampleTestForm(forms.Form):
    full_name = forms.CharField(label="Full Name", required=True, help_text="Enter legal name.")
    email = forms.EmailField(label="Email Address", required=False)


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
class SharedDesignSystemTests(TestCase):
    """Focused unit and integration tests for KAN-38 Shared Design System."""

    @classmethod
    def setUpTestData(cls):
        cls.hospital = HospitalSettings.objects.create(
            pk=1,
            name="Vedant Test Hospital",
            address="Test Road, Lucknow",
            emergency_phone="102",
        )
        for name in ("Administrator", "Doctor", "Reception", "Pharmacy"):
            Group.objects.create(name=name)

        cls.superuser = User.objects.create_superuser("super_admin")
        cls.doctor = User.objects.create_user("doctor_user")
        cls.doctor.groups.add(Group.objects.get(name="Doctor"))
        StaffProfile.objects.create(user=cls.doctor, employee_id="DOC-99")

        cls.reception = User.objects.create_user("rec_user")
        cls.reception.groups.add(Group.objects.get(name="Reception"))
        StaffProfile.objects.create(user=cls.reception, employee_id="REC-99")

        cls.patient_user = User.objects.create_user("patient_user")
        cls.patient = Patient.objects.create(mrn="DS-001", full_name="DS Test Patient")
        PatientAccount.objects.create(user=cls.patient_user, patient=cls.patient, is_verified=True)

    def setUp(self):
        self.rf = RequestFactory()

    # --- 1. Design Tokens and CSS Asset Loading ---

    def test_css_tokens_defined_in_style_sheet(self):
        """Assert CSS custom properties for color, typography, spacing, focus, and reduced motion exist."""
        style_path = os.path.join(os.path.dirname(__file__), "static", "core", "style.css")
        with open(style_path, "r", encoding="utf-8") as f:
            css = f.read()

        # Token checks
        self.assertIn("--color-primary:", css)
        self.assertIn("--color-secondary:", css)
        self.assertIn("--color-tertiary:", css)
        self.assertIn("--font-sans:", css)
        self.assertIn("--font-size-base:", css)
        self.assertIn("--space-4:", css)
        self.assertIn("--radius-md:", css)
        self.assertIn("--focus-ring:", css)
        self.assertIn("--target-min:", css)

        # Accessibility checks in CSS
        self.assertIn(":focus-visible", css)
        self.assertIn(".hms-skip-link", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)

        # Portal theme accent hooks
        self.assertIn('[data-portal="admin"]', css)
        self.assertIn('[data-portal="staff"]', css)
        self.assertIn('[data-portal="store"]', css)
        self.assertIn('[data-portal="patient"]', css)
        self.assertIn('[data-portal="agent"]', css)

    # --- 2. Base Shell & Accessibility Landmarks ---

    def test_base_template_includes_skip_link_and_landmarks(self):
        """Assert base layout has skip link and main landmark with id."""
        request = self.rf.get("/")
        request.user = self.doctor
        request.portal = "staff"
        rendered = render_to_string("core/base.html", {"hospital": self.hospital}, request=request)

        self.assertIn('class="hms-skip-link"', rendered)
        self.assertIn('href="#main-content"', rendered)
        self.assertIn('id="main-content"', rendered)
        self.assertIn('data-portal="staff"', rendered)

    def test_auth_base_template_includes_skip_link(self):
        """Assert auth layout has skip link and target container."""
        request = self.rf.get("/accounts/login/")
        request.user = User.objects.none()
        request.portal = "staff"
        rendered = render_to_string("registration/base.html", {"hospital": self.hospital}, request=request)

        self.assertIn('class="hms-skip-link"', rendered)
        self.assertIn('href="#auth-content"', rendered)
        self.assertIn('id="auth-content"', rendered)

    # --- 3. Portal Branding & Role Labels Context Processor ---

    def test_context_processor_portal_branding_and_titles(self):
        """Assert context processor sets correct titles, brand URLs, and role labels per portal."""
        test_matrix = [
            ("admin", self.superuser, "Hospital Management & CMS", "/admin/", "System Administrator"),
            ("staff", self.doctor, "Clinical Operations", "/", "Attending Doctor"),
            ("staff", self.reception, "Clinical Operations", "/", "Front Desk & Reception"),
            ("patient", self.patient_user, "Patient Portal", "/", "Verified Patient"),
        ]

        for portal_name, user, expected_title, expected_url, expected_role in test_matrix:
            with self.subTest(portal=portal_name, user=user.username):
                request = self.rf.get("/")
                request.user = user
                request.portal = portal_name

                ctx = hospital_context(request)
                self.assertEqual(ctx["portal"], portal_name)
                self.assertEqual(ctx["portal_title"], expected_title)
                self.assertEqual(ctx["portal_brand_url"], expected_url)
                self.assertEqual(ctx["user_role_label"], expected_role)

    # --- 4. Reusable Component Includes ---

    def test_alert_component_rendering(self):
        """Assert alert component renders all variants, titles, and dismiss button."""
        variants = ["info", "success", "warning", "danger"]
        for var in variants:
            with self.subTest(variant=var):
                rendered = render_to_string(
                    "core/components/alert.html",
                    {"level": var, "title": f"Test {var}", "message": "Test message", "dismissible": True},
                )
                self.assertIn(f"hms-alert-{var}", rendered)
                self.assertIn(f"Test {var}", rendered)
                self.assertIn("Test message", rendered)
                self.assertIn('role="alert"', rendered)
                self.assertIn('class="hms-alert-close"', rendered)

    def test_badge_component_rendering(self):
        """Assert badge component renders variants and status dots."""
        rendered = render_to_string(
            "core/components/badge.html",
            {"variant": "success", "label": "Active", "dot": True},
        )
        self.assertIn("hms-badge-success", rendered)
        self.assertIn("hms-status-dot-success", rendered)
        self.assertIn("Active", rendered)

    def test_empty_state_component_rendering(self):
        """Assert empty state component renders title, description, and CTA link."""
        rendered = render_to_string(
            "core/components/empty_state.html",
            {
                "icon": "search",
                "title": "No records found",
                "description": "Try modifying your search criteria.",
                "action_url": "/reset/",
                "action_label": "Clear search",
            },
        )
        self.assertIn("No records found", rendered)
        self.assertIn("Try modifying your search criteria.", rendered)
        self.assertIn('href="/reset/"', rendered)
        self.assertIn("Clear search", rendered)

    def test_card_component_rendering(self):
        """Assert card component renders header, body, and footer."""
        rendered = render_to_string(
            "core/components/card.html",
            {
                "kicker": "Analytics",
                "title": "Monthly Summary",
                "subtitle": "Overview of admissions",
                "badge": "Updated",
                "badge_variant": "info",
                "content": "<p>Body content</p>",
                "footer": "<span>Last updated today</span>",
            },
        )
        self.assertIn("Monthly Summary", rendered)
        self.assertIn("Analytics", rendered)
        self.assertIn("Overview of admissions", rendered)
        self.assertIn("Updated", rendered)
        self.assertIn("<p>Body content</p>", rendered)
        self.assertIn("Last updated today", rendered)

    def test_pagination_component_rendering(self):
        """Assert pagination component renders accessible nav, controls, and page indicator."""
        paginator = Paginator(list(range(100)), 10)
        page_obj = paginator.page(2)

        rendered = render_to_string(
            "core/components/pagination.html",
            {"page_obj": page_obj, "query": "test"},
        )
        self.assertIn('class="hms-pagination"', rendered)
        self.assertIn('aria-label="Pagination navigation"', rendered)
        self.assertIn("Page 2 of 10", rendered)
        self.assertIn('href="?page=1&q=test"', rendered)
        self.assertIn('href="?page=3&q=test"', rendered)

    def test_form_fields_component_rendering(self):
        """Assert form_fields component renders labels, inputs, required asterisks, and field errors."""
        form = SampleTestForm(data={"full_name": ""})  # Triggers required validation error
        self.assertFalse(form.is_valid())

        rendered = render_to_string(
            "core/components/form_fields.html",
            {"form": form},
        )
        self.assertIn('class="hms-form-group', rendered)
        self.assertIn('class="hms-form-label"', rendered)
        self.assertIn('class="hms-form-required"', rendered)
        self.assertIn('class="hms-form-help"', rendered)
        self.assertIn('class="hms-form-field-error"', rendered)
        self.assertIn('role="alert"', rendered)

    def test_dialog_component_rendering(self):
        """Assert dialog component renders HTML5 dialog with accessible labels and actions."""
        rendered = render_to_string(
            "core/components/dialog.html",
            {
                "dialog_id": "delete-modal",
                "title": "Confirm Delete",
                "message": "Are you sure you want to delete this record?",
                "danger": True,
                "confirm_label": "Delete Record",
                "confirm_action_url": "/delete/1/",
            },
        )
        self.assertIn('<dialog id="delete-modal"', rendered)
        self.assertIn('aria-labelledby="delete-modal-title"', rendered)
        self.assertIn("Confirm Delete", rendered)
        self.assertIn("Are you sure you want to delete this record?", rendered)
        self.assertIn('href="/delete/1/"', rendered)
        self.assertIn("btn-stitch-danger", rendered)
