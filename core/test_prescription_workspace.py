from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    AuditEvent,
    Consultation,
    Medicine,
    NumberSequence,
    Patient,
    Prescription,
    PrescriptionItem,
    StaffProfile,
    VisitType,
)
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
    ALLOWED_HOSTS=["testserver", ".hms.test"],
)
class PrescriptionWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        NumberSequence.objects.create(
            code="PRESCRIPTION",
            prefix="RX-",
            next_value=200,
        )

        # Attending Doctor 1
        cls.doc1_user = User.objects.create_user("doc1_user", password="password")
        cls.doc1_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc1_profile = StaffProfile.objects.create(
            user=cls.doc1_user,
            employee_id="DOC001",
        )

        # Doctor 2 (unassigned)
        cls.doc2_user = User.objects.create_user("doc2_user", password="password")
        cls.doc2_user.groups.add(Group.objects.get(name="Doctor"))
        cls.doc2_profile = StaffProfile.objects.create(
            user=cls.doc2_user,
            employee_id="DOC002",
        )

        # Pharmacy user
        cls.pharmacy_user = User.objects.create_user("pharmacy_user", password="password")
        cls.pharmacy_user.groups.add(Group.objects.get(name="Pharmacy"))
        cls.pharmacy_profile = StaffProfile.objects.create(
            user=cls.pharmacy_user,
            employee_id="PHM001",
        )

        # Administrator
        cls.admin_user = User.objects.create_user("admin_user", password="password", is_staff=True)
        cls.admin_user.groups.add(Group.objects.get(name="Administrator"))
        cls.admin_profile = StaffProfile.objects.create(
            user=cls.admin_user,
            employee_id="ADM001",
        )

        # Reception
        cls.reception_user = User.objects.create_user("reception_user", password="password")
        cls.reception_user.groups.add(Group.objects.get(name="Reception"))
        cls.reception_profile = StaffProfile.objects.create(
            user=cls.reception_user,
            employee_id="REC001",
        )

        # Patient
        cls.patient = Patient.objects.create(
            mrn="PAT-000201",
            full_name="Helen Prescription",
            allergy_safety_notes="<script>alert('xss')</script>Aspirin allergy",
        )
        cls.visit_type = VisitType.objects.create(name="Consultation", code="CONS")

        cls.appointment = Appointment.objects.create(
            patient=cls.patient,
            doctor=cls.doc1_profile,
            visit_type=cls.visit_type,
            scheduled_at=timezone.now(),
            status=Appointment.Status.IN_PROGRESS,
            started_at=timezone.now(),
        )

        cls.consultation = Consultation.objects.create(
            appointment=cls.appointment,
            patient=cls.patient,
            doctor=cls.doc1_profile,
            clinical_notes="Prescription testing consultation notes",
            diagnosis="Bacterial Infection",
        )

        # Medicines
        cls.med_active = Medicine.objects.create(
            code="MED-ACT",
            generic_name="Azithromycin",
            brand_name="Azi 500",
            dosage_form="Tablet",
            strength="500mg",
            unit="strip",
            is_active=True,
        )
        cls.med_inactive = Medicine.objects.create(
            code="MED-INACT",
            generic_name="Discontinued Drug",
            brand_name="OldBrand",
            dosage_form="Tablet",
            strength="100mg",
            unit="strip",
            is_active=False,
        )

        # Prescription authored by Doctor 1
        cls.prescription = Prescription.objects.create(
            number="RX-000201",
            consultation=cls.consultation,
            patient=cls.patient,
            doctor=cls.doc1_profile,
            status=Prescription.Status.ISSUED,
            issued_at=timezone.now(),
        )
        cls.rx_item = PrescriptionItem.objects.create(
            prescription=cls.prescription,
            medicine=cls.med_active,
            dosage="1 tab",
            frequency="Once daily",
            duration="5 days",
            quantity=5,
            instructions="Take after food <script>alert(1)</script>",
        )

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(
            f"/prescriptions/{self.prescription.pk}/print/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertRedirects(
            response,
            f"/accounts/login/?next=/prescriptions/{self.prescription.pk}/print/",
            fetch_redirect_response=False,
        )

    def test_reception_cannot_view_or_print_prescription(self):
        self.client.force_login(self.reception_user)
        response = self.client.get(
            f"/prescriptions/{self.prescription.pk}/print/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 403)

    def test_doctor_cannot_print_other_doctors_prescriptions(self):
        # Doctor 2 is not the author of this prescription
        self.client.force_login(self.doc2_user)
        response = self.client.get(
            f"/prescriptions/{self.prescription.pk}/print/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 404)

    def test_authoring_doctor_can_print_with_escaped_html(self):
        self.client.force_login(self.doc1_user)
        response = self.client.get(
            f"/prescriptions/{self.prescription.pk}/print/",
            HTTP_HOST="staff.hms.test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RX-000201")
        self.assertContains(response, "Azithromycin 500mg")
        # Ensure user input is HTML escaped, not raw executable scripts
        self.assertNotContains(response, "<script>alert('xss')</script>")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="clinical.prescription_printed",
                target_id=str(self.prescription.pk),
            ).exists()
        )

    def test_pharmacy_and_admin_can_view_issued_prescription_for_print(self):
        for user in (self.pharmacy_user, self.admin_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(
                    f"/prescriptions/{self.prescription.pk}/print/",
                    HTTP_HOST="staff.hms.test",
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "RX-000201")

    def test_prescription_formset_excludes_inactive_medicines(self):
        from core.forms import PrescriptionItemFormSet
        formset = PrescriptionItemFormSet()
        medicine_field = formset.forms[0].fields["medicine"]
        qs = medicine_field.queryset
        self.assertIn(self.med_active, qs)
        self.assertNotIn(self.med_inactive, qs)

    def test_pharmacy_queue_shows_issued_prescriptions(self):
        self.client.force_login(self.pharmacy_user)
        response = self.client.get("/pharmacy/prescriptions/", HTTP_HOST="staff.hms.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RX-000201")
        self.assertContains(response, "Helen Prescription")
