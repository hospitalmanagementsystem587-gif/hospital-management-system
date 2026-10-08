from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from core.models import Department, DoctorSpecialty, Price, Specialty, StaffProfile
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
class ConsultationPricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        configure_role_permissions()

        # Specialty
        cls.cardiology = Specialty.objects.create(
            code="CARDIO_OPD",
            name="Clinical Cardiology",
        )
        cls.cardio_ct = ContentType.objects.get_for_model(cls.cardiology)

        # Specialty default price: INR 800 initial, INR 500 follow_up
        cls.p_spec_initial = Price.objects.create(
            price_type=Price.PriceType.CONSULTATION,
            content_type=cls.cardio_ct,
            object_id=cls.cardiology.pk,
            scope="initial",
            amount=Decimal("800.00"),
            currency="INR",
            effective_from=date.today() - timedelta(days=10),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        cls.p_spec_followup = Price.objects.create(
            price_type=Price.PriceType.CONSULTATION,
            content_type=cls.cardio_ct,
            object_id=cls.cardiology.pk,
            scope="follow_up",
            amount=Decimal("500.00"),
            currency="INR",
            effective_from=date.today() - timedelta(days=10),
            status=Price.Status.APPROVED,
            is_active=True,
        )

        # Department
        cls.dept = Department.objects.create(
            code="CARDIO_DEPT",
            name="Department of Cardiology",
            is_active=True,
        )

        # Doctor user & profile (legacy default fee 600)
        cls.doc_user = User.objects.create_user(
            username="cardiologist_dr_rao",
            email="rao@test.hms",
            password="DocPassword123!",
            is_staff=True,
        )
        doctor_group = Group.objects.get(name="Doctor")
        cls.doc_user.groups.add(doctor_group)

        cls.doctor = StaffProfile.objects.create(
            user=cls.doc_user,
            employee_id="DOC-RAO-01",
            department=cls.dept,
            consultation_fee=600,
            is_public=True,
        )
        DoctorSpecialty.objects.create(
            doctor=cls.doctor,
            specialty=cls.cardiology,
            is_primary=True,
        )
        cls.doc_ct = ContentType.objects.get_for_model(cls.doctor)

    def test_specialty_pricing_applies_when_no_doctor_override_exists(self):
        """Doctor inherits specialty initial and follow-up prices when no doctor-specific price exists."""
        initial_fee = self.doctor.get_consultation_price(scope="initial")
        followup_fee = self.doctor.get_consultation_price(scope="follow_up")
        self.assertEqual(initial_fee, Decimal("800.00"))
        self.assertEqual(followup_fee, Decimal("500.00"))

    def test_doctor_specific_override_takes_precedence(self):
        """Doctor-specific price overrides the specialty price."""
        Price.objects.create(
            price_type=Price.PriceType.CONSULTATION,
            content_type=self.doc_ct,
            object_id=self.doctor.pk,
            scope="initial",
            amount=Decimal("1200.00"),
            currency="INR",
            effective_from=date.today() - timedelta(days=5),
            status=Price.Status.APPROVED,
            is_active=True,
        )
        initial_fee = self.doctor.get_consultation_price(scope="initial")
        self.assertEqual(initial_fee, Decimal("1200.00"))

        # Follow-up still inherits specialty follow-up (500) because doctor only overrode initial
        followup_fee = self.doctor.get_consultation_price(scope="follow_up")
        self.assertEqual(followup_fee, Decimal("500.00"))

    def test_legacy_consultation_fee_fallback_when_no_canonical_prices_exist(self):
        """Doctor without specialty or canonical prices falls back to StaffProfile.consultation_fee."""
        general_doc_user = User.objects.create_user(
            username="general_doc",
            email="gen@test.hms",
            password="Password123!",
            is_staff=True,
        )
        general_doctor = StaffProfile.objects.create(
            user=general_doc_user,
            employee_id="DOC-GEN-01",
            consultation_fee=450,
        )
        fee = general_doctor.get_consultation_price(scope="initial")
        self.assertEqual(fee, Decimal("450.00"))

    def test_doctor_api_reflects_resolved_canonical_price(self):
        """Public Doctor API exposes the resolved initial consultation price."""
        response = self.client.get(f"/api/v1/doctors/{self.doctor.pk}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["consultation_fee"], 800)
