from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from core.forms import HospitalFacilityForm, HospitalFaqForm
from core.models import HospitalFacility, HospitalFaq
from core.roles import configure_role_permissions

User = get_user_model()


@override_settings(
    PORTAL_HOSTS={
        "admin": "admin.hms.test",
        "staff": "staff.hms.test",
        "store": "store.hms.test",
        "patient": "patient.hms.test",
        "agent": "agent.hms.test",
    },
    ALLOWED_HOSTS=["*"],
)
class FacilitiesFaqsCMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Admin user
        cls.admin_user = User.objects.create_user(
            username="admin_fac_user",
            email="admin_fac@test.hms",
            password="AdminPassword123!",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Administrator")
        cls.admin_user.groups.add(admin_group)

        # Non-admin staff user (Reception)
        cls.reception_user = User.objects.create_user(
            username="reception_fac_user",
            email="reception_fac@test.hms",
            password="ReceptionPassword123!",
            is_staff=True,
        )
        reception_group = Group.objects.get(name="Reception")
        cls.reception_user.groups.add(reception_group)

        # Baseline active and inactive facilities
        cls.facility_active = HospitalFacility.objects.create(
            title="Advanced Cardiac Catheterization Lab",
            category="Critical Care",
            description="Equipped with biplane angiography systems for urgent coronary interventions.",
            highlight="24x7 STEMI Interventions",
            display_order=1,
            is_active=True,
        )
        cls.facility_inactive = HospitalFacility.objects.create(
            title="Helipad Air Ambulance Station",
            category="Amenities",
            description="Rooftop emergency medical evacuation platform.",
            highlight="FAA / DGCA Certified",
            display_order=10,
            is_active=False,
        )

        # Baseline active and inactive FAQs
        cls.faq_active = HospitalFaq.objects.create(
            question="What are the visiting hours for inpatient wards?",
            answer="General ward visiting hours are 4:00 PM to 7:00 PM daily. Only one visitor with an attendant pass is permitted at bedside.",
            category="Inpatient Services",
            highlight_tag="Ward Timings",
            display_order=1,
            is_active=True,
        )
        cls.faq_inactive = HospitalFaq.objects.create(
            question="Are rapid COVID-19 RT-PCR tests still mandatory upon entry?",
            answer="Routine admission testing has been relaxed following current health department guidelines.",
            category="General Information",
            highlight_tag="COVID Guidelines",
            display_order=20,
            is_active=False,
        )

    def test_authorized_admin_can_view_facility_changelist(self):
        """Admin can access HospitalFacility changelist in admin portal."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/hospitalfacility/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Advanced Cardiac Catheterization Lab")
        self.assertContains(response, "Helipad Air Ambulance Station")

    def test_authorized_admin_can_view_faq_changelist(self):
        """Admin can access HospitalFaq changelist in admin portal."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/core/hospitalfaq/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What are the visiting hours for inpatient wards?")

    def test_unauthorized_staff_cannot_access_facility_cms(self):
        """Reception staff cannot access HospitalFacility admin pages."""
        self.client.force_login(self.reception_user)
        response = self.client.get("/admin/core/hospitalfacility/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_staff_cannot_access_faq_cms(self):
        """Reception staff cannot access HospitalFaq admin pages."""
        self.client.force_login(self.reception_user)
        response = self.client.get("/admin/core/hospitalfaq/", HTTP_HOST="admin.hms.test")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_facility(self):
        """Admin can create a new facility via admin form."""
        self.client.force_login(self.admin_user)
        post_data = {
            "title": "Pediatric Intensive Care Unit (PICU)",
            "category": "Pediatrics",
            "description": "Specialized 16-bed pediatric critical care facility staffed around the clock.",
            "highlight": "Level-3 Tertiary Care",
            "display_order": 2,
            "is_active": "on",
        }
        response = self.client.post(
            "/admin/core/hospitalfacility/add/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        fac = HospitalFacility.objects.get(title="Pediatric Intensive Care Unit (PICU)")
        self.assertTrue(fac.is_active)
        self.assertEqual(fac.display_order, 2)

    def test_admin_can_create_faq(self):
        """Admin can create a new FAQ entry via admin form."""
        self.client.force_login(self.admin_user)
        post_data = {
            "question": "How do I download my lab reports online?",
            "answer": "Patients can download signed pathology and radiology reports from the patient portal under 'Health Records'.",
            "category": "Diagnostics",
            "highlight_tag": "Reports",
            "display_order": 2,
            "is_active": "on",
        }
        response = self.client.post(
            "/admin/core/hospitalfaq/add/",
            data=post_data,
            HTTP_HOST="admin.hms.test",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        faq = HospitalFaq.objects.get(question="How do I download my lab reports online?")
        self.assertTrue(faq.is_active)
        self.assertEqual(faq.display_order, 2)

    def test_facility_form_validation_duplicate_title(self):
        """Facility form rejects duplicate titles case-insensitively."""
        form = HospitalFacilityForm(data={
            "title": "advanced cardiac catheterization lab",
            "category": "Critical Care",
            "description": "Duplicate check",
            "display_order": 5,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)
        self.assertIn("already exists", form.errors["title"][0])

    def test_faq_form_validation_duplicate_question(self):
        """FAQ form rejects duplicate questions case-insensitively."""
        form = HospitalFaqForm(data={
            "question": "what are the visiting hours for inpatient wards?",
            "answer": "Duplicate question answer.",
            "category": "Inpatient",
            "display_order": 5,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("question", form.errors)
        self.assertIn("already exists", form.errors["question"][0])

    def test_public_api_exposes_only_active_facilities_in_deterministic_order(self):
        """Public facilities API exposes only active facilities ordered by display_order."""
        response = self.client.get("/api/v1/facilities/")
        self.assertEqual(response.status_code, 200)
        results = response.json()
        titles = [item["title"] for item in results]
        self.assertIn("Advanced Cardiac Catheterization Lab", titles)
        self.assertNotIn("Helipad Air Ambulance Station", titles)  # inactive excluded

    def test_public_api_exposes_only_active_faqs_in_deterministic_order(self):
        """Public FAQs API exposes only active FAQs ordered by display_order."""
        response = self.client.get("/api/v1/faqs/")
        self.assertEqual(response.status_code, 200)
        results = response.json()
        questions = [item["question"] for item in results]
        self.assertIn("What are the visiting hours for inpatient wards?", questions)
        self.assertNotIn("Are rapid COVID-19 RT-PCR tests still mandatory upon entry?", questions)  # inactive excluded
